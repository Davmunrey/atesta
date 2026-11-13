"""Public interface of the billing module.

The entitlement checks below are the ONLY place the API and UI decide access (ADR-009). Prices
and plan contents are hypotheses from the business plan. Framework grants are data in
catalog/plans.yaml, so selling a new pack or level needs no code change (MF-03, rule 9).
"""

import os
from collections.abc import Mapping
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any

import yaml


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

Grants = Mapping[str, Mapping[str, str | frozenset[str]]]
_REPO = Path(__file__).resolve().parents[6]


def has_feature(plan: Plan, feature: Feature, addons: frozenset[Feature] = frozenset()) -> bool:
    """True if the plan includes the feature or it was bought as an add-on."""
    return feature in PLAN_FEATURES[plan] or feature in addons


def connector_limit(plan: Plan) -> int | None:
    """Max connectors for the plan; None means unlimited."""
    return PLAN_CONNECTOR_LIMIT[plan]


def parse_grants(raw: Any, known_frameworks: frozenset[str]) -> tuple[Grants, Grants]:
    """Validate plans.yaml: every plan present, known pack ids, values "all" or a str list."""

    def section(entries: Any, where: str) -> dict[str, dict[str, str | frozenset[str]]]:
        if not isinstance(entries, dict):
            raise ValueError(f"{where} must be a mapping")
        out: dict[str, dict[str, str | frozenset[str]]] = {}
        for name, frameworks in entries.items():
            if not isinstance(frameworks, dict):
                raise ValueError(f"{where}.{name} must be a mapping")
            out[str(name)] = {}
            for key, value in frameworks.items():
                if key not in known_frameworks:
                    raise ValueError(f"{where}.{name}: unknown framework {key!r}")
                if value != "all" and not (
                    isinstance(value, list) and all(isinstance(v, str) for v in value)
                ):
                    raise ValueError(f"{where}.{name}.{key}: use 'all' or a list of strings")
                out[str(name)][key] = "all" if value == "all" else frozenset(value)
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
    granted = [plans[plan].get(framework_key)]
    granted += [addon_grants.get(a, {}).get(framework_key) for a in addons]
    return any(_allows(g, applies_to) for g in granted)
