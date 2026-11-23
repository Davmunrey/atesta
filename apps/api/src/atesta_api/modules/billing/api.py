"""Public interface of the billing module.

The entitlement checks below are the ONLY place the API and UI decide access (ADR-009). Prices
and plan contents are hypotheses from the business plan. Framework grants are data in
catalog/plans.yaml, so selling a new pack or level needs no code change (MF-03, rule 9).
Routes enforce them with the require_* checks (billing-entitlements spec).
"""

import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.billing.models import Subscription


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
