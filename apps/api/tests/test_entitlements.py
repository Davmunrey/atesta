from atesta_api.modules.billing.api import Feature, Plan, connector_limit, has_feature


def test_starter_lacks_evidence_export() -> None:
    assert not has_feature(Plan.STARTER, Feature.EVIDENCE_EXPORT)


def test_addon_unlocks_feature() -> None:
    assert has_feature(Plan.PRO, Feature.NIS2, addons=frozenset({Feature.NIS2}))


def test_business_has_everything() -> None:
    assert all(has_feature(Plan.BUSINESS, f) for f in Feature)


def test_connector_limits() -> None:
    assert connector_limit(Plan.STARTER) == 1
    assert connector_limit(Plan.BUSINESS) is None
