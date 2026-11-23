"""Official packs account for every unit of their source (content model v2) and keep the
official wording. Expected units and quotes come from the captured sources in each pack's
SOURCES.md, not from memory."""

import json
from functools import cache
from pathlib import Path

import pytest
from atesta_api.modules.compliance.catalog import Catalog, read_catalog
from atesta_api.modules.compliance.catalog_schema import Pack

ROOT = Path(__file__).resolve().parents[3]


@cache
def catalog() -> Catalog:
    expected: set[str] = set()
    for provider in ("m365", "googleworkspace"):
        path = ROOT / "scanner/expected/5.49.0" / f"{provider}.json"
        expected.update(json.loads(path.read_text())[provider])
    return read_catalog(ROOT / "catalog", expected_checks=expected, engine_version="5.49.0")


def pack(key: str) -> Pack:
    return next(p for p in catalog().packs if p.metadata.id == key)


def _articles(units: set[str]) -> set[str]:
    """`art21.1-4` and `art21.5` together account for article 21."""
    return {u.split(".")[0] for u in units}


@pytest.mark.parametrize(
    ("key", "units"),
    [
        ("nis2", {f"art{n}" for n in range(1, 47)} | {"annex1", "annex2", "annex3"}),
        (
            "ens_rd311_2022",
            {f"art{n}" for n in range(1, 42)}
            | {"da1", "da2", "da3", "dt", "dd", "df1", "df2", "df3"}
            | {f"annex{n}" for n in range(1, 5)},
        ),
    ],
)
def test_the_ledger_accounts_for_every_unit_of_the_source(key: str, units: set[str]) -> None:
    coverage = pack(key).coverage
    assert coverage is not None
    listed = {u for e in coverage.entries for u in e.units}
    assert _articles(listed) == units


def test_nis2_keeps_the_official_spanish_and_english_text() -> None:
    nis2 = pack("nis2")
    requirements = {r.id: r for r in nis2.requirements}
    assert len(requirements) == 23
    assert {f"art21.2{letter}" for letter in "abcdefghij"} <= requirements.keys()
    assert requirements["art21.2b"].title_es == "La gestión de incidentes"
    assert requirements["art21.2b"].title_en == "Incident handling"
    early = requirements["art23.4a"].attributes
    assert "veinticuatro horas" in early.official_text_es
    assert "within 24 hours of becoming aware of the significant incident" in (
        early.official_text_en or ""
    )
    mfa = requirements["art21.2j"].attributes.official_text_es
    assert "autenticación multifactorial o de autenticación continua" in mfa
    assert all(r.attributes.official_text_en for r in nis2.requirements)
    assert all(r.attributes.selection_basis is None for r in nis2.requirements)


def test_nis2_mappings_are_unreviewed_candidates_with_documentary_review() -> None:
    nis2 = pack("nis2")
    assert nis2.metadata.attributes.assessment_enabled is False
    assert all(m.reviewed_by is None for m in nis2.mappings)
    manual = {c.id for c in catalog().controls.values() if c.manual}
    for requirement in nis2.requirements:
        controls = {m.control_id for m in nis2.mappings if m.requirement_id == requirement.id}
        assert controls & manual, requirement.id


def test_group_headings_have_the_official_english_heading_when_one_exists() -> None:
    groups = {g.prefix: g for g in pack("nis2").metadata.attributes.groups_es}
    assert groups["art23"].title == "Obligaciones de notificación"
    assert groups["art23"].title_en == "Reporting obligations"
