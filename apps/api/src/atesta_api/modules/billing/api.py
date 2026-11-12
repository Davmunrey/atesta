"""Public interface of the billing module.

The entitlements check below is the ONLY place the API and UI decide access to features
(ADR-009). Prices and plan contents are hypotheses from the business plan.
"""

from enum import StrEnum


class Plan(StrEnum):
    STARTER = "starter"
    PRO = "pro"
    BUSINESS = "business"


class Feature(StrEnum):
    ENS_MEDIUM = "ens_medium"
    ENS_HIGH = "ens_high"
    DAILY_MONITORING = "daily_monitoring"
    EVIDENCE_EXPORT = "evidence_export"
    POLICY_AI_REVIEW = "policy_ai_review"
    NIS2 = "nis2"
    QUESTIONNAIRE_AUTOFILL = "questionnaire_autofill"
    TRUST_CENTER = "trust_center"


PLAN_FEATURES: dict[Plan, frozenset[Feature]] = {
    Plan.STARTER: frozenset({Feature.ENS_MEDIUM}),
    Plan.PRO: frozenset(
        {
            Feature.ENS_MEDIUM,
            Feature.DAILY_MONITORING,
            Feature.EVIDENCE_EXPORT,
            Feature.POLICY_AI_REVIEW,
        }
    ),
    Plan.BUSINESS: frozenset(Feature),
}

PLAN_CONNECTOR_LIMIT: dict[Plan, int | None] = {
    Plan.STARTER: 1,
    Plan.PRO: 3,
    Plan.BUSINESS: None,
}


def has_feature(plan: Plan, feature: Feature, addons: frozenset[Feature] = frozenset()) -> bool:
    """True if the plan includes the feature or it was bought as an add-on."""
    return feature in PLAN_FEATURES[plan] or feature in addons


def connector_limit(plan: Plan) -> int | None:
    """Max connectors for the plan; None means unlimited."""
    return PLAN_CONNECTOR_LIMIT[plan]
