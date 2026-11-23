import pytest
from atesta_api.modules.billing.api import (
    Feature,
    Plan,
    connector_limit,
    has_feature,
    has_framework,
    parse_grants,
)

KNOWN = frozenset({"fw_a", "fw_b"})  # synthetic pack ids (rule 10)
RAW = {
    "plans": {"starter": {"fw_a": ["low"]}, "pro": {"fw_a": "all"}, "business": {"fw_a": "all"}},
    "addons": {"second_pack": {"fw_b": "all"}},
}


def test_starter_lacks_evidence_export() -> None:
    assert not has_feature(Plan.STARTER, Feature.EVIDENCE_EXPORT)


def test_addon_unlocks_feature() -> None:
    addons = frozenset({Feature.TRUST_CENTER})
    assert has_feature(Plan.PRO, Feature.TRUST_CENTER, addons=addons)


def test_business_has_everything() -> None:
    assert all(has_feature(Plan.BUSINESS, f) for f in Feature)


def test_connector_limits() -> None:
    assert connector_limit(Plan.STARTER) == 1
    assert connector_limit(Plan.BUSINESS) is None


def test_framework_grants_from_data(monkeypatch: pytest.MonkeyPatch) -> None:
    from atesta_api.modules.billing import api

    monkeypatch.setattr(api, "_grants", lambda: parse_grants(RAW, KNOWN))
    assert has_framework(Plan.STARTER, "fw_a", "low")
    assert not has_framework(Plan.STARTER, "fw_a", "high")
    assert has_framework(Plan.PRO, "fw_a", "high")
    assert not has_framework(Plan.PRO, "fw_b")
    assert has_framework(Plan.PRO, "fw_b", addons=frozenset({"second_pack"}))


@pytest.mark.parametrize(
    "raw",
    [
        {"plans": {"starter": {}, "pro": {}}},
        {"plans": {**RAW["plans"], "starter": {"unknown": "all"}}},
        {"plans": {**RAW["plans"], "starter": {"fw_a": "some"}}},
    ],
)
def test_invalid_grants_are_refused(raw: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        parse_grants(raw, KNOWN)


def test_repository_plans_file_is_valid() -> None:
    from atesta_api.modules.billing import api

    api._grants.cache_clear()
    plans, _ = api._grants()
    assert set(plans) == {p.value for p in Plan}


def test_a_plan_may_grant_every_framework(monkeypatch: pytest.MonkeyPatch) -> None:
    from atesta_api.modules.billing import api

    raw = {"plans": {**RAW["plans"], "business": "all"}}
    monkeypatch.setattr(api, "_grants", lambda: parse_grants(raw, KNOWN))
    assert has_framework(Plan.BUSINESS, "fw_b")
    assert has_framework(Plan.BUSINESS, "a_pack_added_later")
    assert not has_framework(Plan.STARTER, "fw_b")


def test_pilot_organizations_default_to_business() -> None:
    from atesta_api.modules.billing.api import DEFAULT_PLAN

    assert DEFAULT_PLAN is Plan.BUSINESS


def test_feature_addons_are_the_feature_values_only() -> None:
    from atesta_api.modules.billing.api import Entitlements

    granted = Entitlements(Plan.STARTER, frozenset({"evidence_export", "second_pack"}))
    assert granted.feature_addons == frozenset({Feature.EVIDENCE_EXPORT})


def test_repository_grants_follow_the_accepted_hypothesis() -> None:
    """business opens every pack, drafts and synthetic ones too; starter and pro the ENS pack."""
    from atesta_api.modules.billing import api

    api._grants.cache_clear()
    packs = api.known_frameworks(api._catalog())
    assert "ens_rd311_2022" in packs
    assert all(has_framework(Plan.BUSINESS, p) for p in packs | {"synthetic_alpha"})
    assert has_framework(Plan.PRO, "ens_rd311_2022")
    assert has_framework(Plan.STARTER, "ens_rd311_2022")
    assert not has_framework(Plan.STARTER, "nis2") and not has_framework(Plan.PRO, "nis2")
