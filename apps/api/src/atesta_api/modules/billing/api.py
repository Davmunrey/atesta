"""Public interface of the billing module.

The entitlement checks below are the ONLY place the API and UI decide access (ADR-009). Prices
and plan contents are hypotheses from the business plan. Framework grants are data in
catalog/plans.yaml, so selling a new pack or level needs no code change (MF-03, rule 9).
Routes enforce them with the require_* checks (billing-entitlements spec).
"""

import os
import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from atesta_api.modules.billing.models import Subscription
from atesta_api.modules.billing.profiles import (
    BillingDetails,
    BillingSummary,
    billing_profile,
    billing_summaries,
    set_billing_profile,
)


class Plan(StrEnum):
    STARTER = "starter"
    PRO = "pro"
    BUSINESS = "business"


class Feature(StrEnum):
    """Framework-agnostic product features only."""

    DAILY_MONITORING = "daily_monitoring"
    EVIDENCE_EXPORT = "evidence_export"
    POLICY_AI_REVIEW = "policy_ai_review"
    QUESTIONNAIRE_AUTOFILL = "questionnaire_autofill"
    TRUST_CENTER = "trust_center"


PLAN_FEATURES: dict[Plan, frozenset[Feature]] = {
    Plan.STARTER: frozenset(),
    Plan.PRO: frozenset(
        {Feature.DAILY_MONITORING, Feature.EVIDENCE_EXPORT, Feature.POLICY_AI_REVIEW}
    ),
    Plan.BUSINESS: frozenset(Feature),
}

PLAN_CONNECTOR_LIMIT: dict[Plan, int | None] = {
    Plan.STARTER: 1,
    Plan.PRO: 3,
    Plan.BUSINESS: None,
}

# An organization without a subscription row: every pilot organization created before
# enforcement keeps everything it used (owner decision, 2026-11-23).
DEFAULT_PLAN = Plan.BUSINESS

FrameworkGrants = Mapping[str, str | frozenset[str]]
Grants = Mapping[str, FrameworkGrants | Literal["all"]]
_REPO = Path(__file__).resolve().parents[6]


def has_feature(plan: Plan, feature: Feature, addons: frozenset[Feature] = frozenset()) -> bool:
    """True if the plan includes the feature or it was bought as an add-on."""
    return feature in PLAN_FEATURES[plan] or feature in addons


def connector_limit(plan: Plan) -> int | None:
    """Max connectors for the plan; None means unlimited."""
    return PLAN_CONNECTOR_LIMIT[plan]


def parse_grants(raw: Any, known_frameworks: frozenset[str]) -> tuple[Grants, Grants]:
    """Validate plans.yaml: every plan present, known pack ids, values "all" or a str list."""

    def section(entries: Any, where: str) -> dict[str, FrameworkGrants | Literal["all"]]:
        if not isinstance(entries, dict):
            raise ValueError(f"{where} must be a mapping")
        out: dict[str, FrameworkGrants | Literal["all"]] = {}
        for name, frameworks in entries.items():
            if frameworks == "all":  # every framework, including packs added later
                out[str(name)] = "all"
                continue
            if not isinstance(frameworks, dict):
                raise ValueError(f"{where}.{name} must be a mapping")
            grants: dict[str, str | frozenset[str]] = {}
            for key, value in frameworks.items():
                if key not in known_frameworks:
                    raise ValueError(f"{where}.{name}: unknown framework {key!r}")
                if value != "all" and not (
                    isinstance(value, list) and all(isinstance(v, str) for v in value)
                ):
                    raise ValueError(f"{where}.{name}.{key}: use 'all' or a list of strings")
                grants[key] = "all" if value == "all" else frozenset(value)
            out[str(name)] = grants
        return out

    plans = section(raw.get("plans"), "plans")
    if set(plans) != {p.value for p in Plan}:
        raise ValueError("plans must list exactly the Plan values")
    return plans, section(raw.get("addons", {}), "addons")


def _catalog() -> Path:
    return Path(os.environ.get("ATESTA_CATALOG_DIR", _REPO / "catalog"))


def known_frameworks(catalog: Path) -> frozenset[str]:
    packs = (catalog / "frameworks").glob("*/pack.yaml")
    return frozenset(
        str(yaml.safe_load(p.read_text())["id"]) for p in packs if p.parent.name != "_template"
    )


@cache
def _grants() -> tuple[Grants, Grants]:
    catalog = _catalog()
    raw = yaml.safe_load((catalog / "plans.yaml").read_text())
    return parse_grants(raw, known_frameworks(catalog))


def _allows(grant: str | frozenset[str] | None, applies_to: str | None) -> bool:
    if grant is None:
        return False
    return grant == "all" or applies_to is None or applies_to in grant


def has_framework(
    plan: Plan,
    framework_key: str,
    applies_to: str | None = None,
    addons: frozenset[str] = frozenset(),
) -> bool:
    """True if the plan or a bought add-on grants the framework (and the applies_to value)."""
    plans, addon_grants = _grants()
    granted = [_grant(plans.get(plan), framework_key)]
    granted += [_grant(addon_grants.get(a), framework_key) for a in addons]
    return any(_allows(g, applies_to) for g in granted)


def _grant(
    grants: FrameworkGrants | Literal["all"] | None, framework_key: str
) -> str | frozenset[str] | None:
    if grants == "all":
        return "all"
    return None if grants is None else grants.get(framework_key)


@dataclass(frozen=True, slots=True)
class Entitlements:
    """An organization's plan and add-ons, as its subscription row (or the default) says."""

    plan: Plan
    addons: frozenset[str] = frozenset()

    @property
    def feature_addons(self) -> frozenset[Feature]:
        return frozenset(f for f in Feature if f.value in self.addons)


def entitlements(session: Session, organization_id: uuid.UUID) -> Entitlements:
    """The organization's subscription, read in its own tenant context (RLS)."""
    row = session.scalar(
        select(Subscription).where(Subscription.organization_id == organization_id)
    )
    if row is None:
        return Entitlements(DEFAULT_PLAN)
    return Entitlements(Plan(row.plan), frozenset(row.addons))


def has_plan(session: Session, organization_id: uuid.UUID) -> bool:
    """Whether the operator has set a plan: it ends the trial's read-only state (owner answer 1).
    Read in the organization's own context."""
    found = session.scalar(
        select(Subscription.organization_id).where(Subscription.organization_id == organization_id)
    )
    return found is not None


def _beyond_plan(limit: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": "billing.plan_limit", "limit": limit})


def require_connector_slot(session: Session, organization_id: uuid.UUID, in_use: int) -> None:
    """Refuse a new connection once the organization holds as many as its plan allows."""
    limit = connector_limit(entitlements(session, organization_id).plan)
    if limit is not None and in_use >= limit:
        raise _beyond_plan("connectors")


def require_feature(session: Session, organization_id: uuid.UUID, feature: Feature) -> None:
    granted = entitlements(session, organization_id)
    if not has_feature(granted.plan, feature, granted.feature_addons):
        raise _beyond_plan(feature.value)


def require_framework(session: Session, organization_id: uuid.UUID, framework_key: str) -> None:
    granted = entitlements(session, organization_id)
    if not has_framework(granted.plan, framework_key, addons=granted.addons):
        raise _beyond_plan("framework")


# --- the operator service (operator-portal spec; an atesta_operator session, ADR-012 am. 8) ---


class UnknownAddonError(ValueError):
    """An add-on that is neither a feature nor a framework add-on in catalog/plans.yaml."""


@dataclass(frozen=True, slots=True)
class SubscriptionInfo:
    plan: Plan
    addons: frozenset[str]
    note: str
    updated_at: datetime


def known_addons() -> frozenset[str]:
    """Feature add-ons and the framework add-ons in catalog/plans.yaml."""
    return frozenset(f.value for f in Feature) | frozenset(_grants()[1])


def subscriptions_for(
    session: Session, org_ids: Collection[uuid.UUID] | None
) -> dict[uuid.UUID, SubscriptionInfo]:
    """Rows only: an organization absent from the result has DEFAULT_PLAN. None reads all."""
    query = select(
        Subscription.organization_id,
        Subscription.plan,
        Subscription.addons,
        Subscription.note,
        Subscription.updated_at,
    )
    if org_ids is not None:
        query = query.where(Subscription.organization_id.in_(org_ids))
    return {
        org: SubscriptionInfo(Plan(plan), frozenset(addons), note, at)
        for org, plan, addons, note, at in session.execute(query)
    }


def set_subscription(
    session: Session, organization_id: uuid.UUID, plan: Plan, addons: frozenset[str], note: str
) -> Plan | None:
    """Upsert the organization's plan; returns the previous one, None when it had no row. The
    next customer request reads it through entitlements(), and a set plan ends the trial."""
    unknown = sorted(addons - known_addons())
    if unknown:
        raise UnknownAddonError(unknown[0])
    previous = session.scalar(
        select(Subscription.plan)
        .where(Subscription.organization_id == organization_id)
        .with_for_update()
    )
    values = {"plan": plan.value, "addons": sorted(addons), "note": note}
    session.execute(
        insert(Subscription)
        .values(organization_id=organization_id, **values)
        .on_conflict_do_update(
            index_elements=[Subscription.organization_id],
            set_={**values, "updated_at": func.now()},
        )
    )
    return None if previous is None else Plan(previous)


__all__ = [
    "DEFAULT_PLAN",
    "BillingDetails",
    "BillingSummary",
    "Entitlements",
    "Feature",
    "Plan",
    "SubscriptionInfo",
    "UnknownAddonError",
    "billing_profile",
    "billing_summaries",
    "connector_limit",
    "entitlements",
    "has_feature",
    "has_framework",
    "has_plan",
    "known_addons",
    "require_connector_slot",
    "require_feature",
    "require_framework",
    "set_billing_profile",
    "set_subscription",
    "subscriptions_for",
]
