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
        path = ROOT / "scanner/expected/5.52.0" / f"{provider}.json"
        expected.update(json.loads(path.read_text())[provider])
    return read_catalog(ROOT / "catalog", expected_checks=expected, engine_version="5.52.0")


def pack(key: str) -> Pack:
    return next(p for p in catalog().packs if p.metadata.id == key)


def _articles(units: set[str]) -> set[str]:
    """`art21.1-4` and `art21.5` together account for article 21."""
    return {u.split(".")[0] for u in units}


@pytest.mark.parametrize(
    ("key", "units"),
    [
        ("nis2", {f"art{n}" for n in range(1, 47)} | {"annex1", "annex2", "annex3"}),
        ("gdpr_art32", {f"art{n}" for n in range(1, 100)}),
        ("dora", {f"art{n}" for n in range(1, 65)}),
        ("nis2_ir_2024_2690", {f"art{n}" for n in range(1, 17)} | {"annex"}),
        ("dora_rts_2024_1774", {f"art{n}" for n in range(1, 43)}),
        (
            "lopdgdd",
            {f"art{n}" for n in range(1, 98)}
            | {"art53bis"}
            | {f"da{n}" for n in range(1, 24)}
            | {f"dt{n}" for n in range(1, 7)}
            | {"dd"}
            | {f"df{n}" for n in range(1, 17)},
        ),
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
    assert all(
        m.reviewed_by in (None, "David Muñoz") for m in nis2.mappings
    )  # signed: test_mapping_signoffs
    manual = {c.id for c in catalog().controls.values() if c.manual}
    for requirement in nis2.requirements:
        controls = {m.control_id for m in nis2.mappings if m.requirement_id == requirement.id}
        assert controls & manual, requirement.id


def test_group_headings_have_the_official_english_heading_when_one_exists() -> None:
    groups = {g.prefix: g for g in pack("nis2").metadata.attributes.groups_es}
    assert groups["art23"].title == "Obligaciones de notificación"
    assert groups["art23"].title_en == "Reporting obligations"


def test_gdpr_keeps_the_official_text_of_articles_32_to_34() -> None:
    gdpr = pack("gdpr_art32")
    requirements = {r.id: r for r in gdpr.requirements}
    assert len(requirements) == 14
    assert "art32.3" not in requirements  # a means to demonstrate compliance, not a duty
    assert (
        requirements["art32.1a"].title_es == "La seudonimización y el cifrado de datos personales"
    )
    assert (
        requirements["art32.1a"].title_en == "The pseudonymisation and encryption of personal data"
    )
    breach = requirements["art33.1"].attributes
    assert "a más tardar 72 horas después de que haya tenido constancia de ella" in (
        breach.official_text_es
    )
    assert "not later than 72 hours after having become aware of it" in (
        breach.official_text_en or ""
    )
    assert gdpr.metadata.attributes.assessment_enabled is False
    assert all(
        m.reviewed_by in (None, "David Muñoz") for m in gdpr.mappings
    )  # signed: test_mapping_signoffs
    manual = {c.id for c in catalog().controls.values() if c.manual}
    for requirement in gdpr.requirements:
        controls = {m.control_id for m in gdpr.mappings if m.requirement_id == requirement.id}
        assert controls & manual, requirement.id


def test_dora_imports_whole_articles_verbatim_in_both_languages() -> None:
    dora = pack("dora")
    requirements = {r.id: r for r in dora.requirements}
    assert len(requirements) == 22
    assert requirements["c5.art30"].title_es == "Cláusulas contractuales fundamentales"
    assert requirements["c5.art30"].title_en == "Key contractual provisions"
    governance = requirements["c2.art5"].attributes
    # The Journal's own wording, including its missing "de": source spelling is never corrected.
    assert governance.official_text_es.startswith(
        "1. A fin lograr un nivel elevado de resiliencia operativa digital"
    )
    assert (governance.official_text_en or "").startswith(
        "1. Financial entities shall have in place an internal governance and control framework"
    )
    assert {g.prefix for g in dora.metadata.attributes.groups_es} == {"c2", "c3", "c4", "c5"}
    assert dora.metadata.attributes.assessment_enabled is False
    assert all(
        m.reviewed_by in (None, "David Muñoz") for m in dora.mappings
    )  # signed: test_mapping_signoffs
    manual = {c.id for c in catalog().controls.values() if c.manual}
    for requirement in dora.requirements:
        controls = {m.control_id for m in dora.mappings if m.requirement_id == requirement.id}
        assert controls & manual, requirement.id


def test_the_nis2_implementing_regulation_keeps_the_official_text() -> None:
    """Quotes from the captured Journal texts (SOURCES.md), Spanish and English."""
    act = pack("nis2_ir_2024_2690")
    requirements = {r.id: r for r in act.requirements}
    assert len(requirements) == 162
    assert {"art2", "1.1.1", "5.2", "7.1", "12.5", "13.3.3"} <= requirements.keys()
    first = requirements["1.1.1"].attributes
    assert first.official_text_es.startswith(
        "A efectos del artículo 21, apartado 2, letra a), de la Directiva (UE) 2022/2555, la"
    )
    assert "\n\nk) indicará la fecha de la aprobación formal" in first.official_text_es
    assert first.official_text_en is not None
    assert first.official_text_en.startswith(
        "For the purpose of Article 21(2), point (a) of Directive (EU) 2022/2555, the policy"
    )
    registry = requirements["5.2"].attributes.official_text_en or ""
    assert registry.startswith(
        "The relevant entities shall maintain and keep up to date a registry"
    )
    assert requirements["art2"].attributes.official_text_en is not None
    assert "‘to the extent feasible’" in requirements["art2"].attributes.official_text_en


def test_lopdgdd_keeps_the_official_spanish_text() -> None:
    """Quotes from the captured BOE consolidated text (SOURCES.md); there is no official English."""
    law = pack("lopdgdd")
    requirements = {r.id: r for r in law.requirements}
    assert set(requirements) == {"art5", "art28", "art31", "art32", "art33", "da1"}
    assert all(
        r.title_en is None and r.attributes.official_text_en is None for r in law.requirements
    )
    assert requirements["da1"].attributes.official_text_es.startswith(
        "1. El Esquema Nacional de Seguridad incluirá las medidas que deban implantarse"
    )
    assert (
        "f) Cuando se produzca un tratamiento masivo"
        in requirements["art28"].attributes.official_text_es
    )


def test_dora_rts_keeps_the_official_text_with_its_corrigendum() -> None:
    """Article 22(d) as corrected by 32024R1774R(02), in both languages (SOURCES.md)."""
    rts = pack("dora_rts_2024_1774")
    requirements = {r.id: r for r in rts.requirements}
    assert len(requirements) == 41
    assert {"t1.art1", "t2c3.art22", "t3c4.art41"} <= requirements.keys()
    article = requirements["t2c3.art22"].attributes
    assert (
        "de conformidad con el artículo 8, apartado 2, del Reglamento Delegado (UE) 2024/1772"
        in (article.official_text_es)
    )
    assert "[artículo [15]" not in article.official_text_es
    assert "in accordance with Article 8(2) of Commission Delegated Regulation (EU) 2024/1772" in (
        article.official_text_en or ""
    )


def test_the_implementing_regulation_shows_its_incident_criteria_verbatim() -> None:
    """Articles 3 to 14 of 2024/2690 are incident criteria, not measures (SOURCES.md)."""
    act = pack("nis2_ir_2024_2690")
    criteria = act.metadata.attributes.incident_criteria
    assert [c.text.section for c in criteria if c.text] == [f"Artículo {n}" for n in range(3, 15)]
    assert all(c.needs == "significant" and c.requirement is None for c in criteria)
    assert not {f"art{n}" for n in range(3, 15)} & {r.id for r in act.requirements}
    first = criteria[0].text
    assert first is not None
    assert first.official_text_es.startswith("1. Un incidente se considerará significativo")
    assert (first.official_text_en or "").startswith("1. An incident shall be considered")


def test_dora_shows_the_major_incident_criteria_of_2024_1772_verbatim() -> None:
    """Articles 1 to 9 of Delegated Regulation (EU) 2024/1772, ES and EN (dora SOURCES.md)."""
    criteria = pack("dora").metadata.attributes.incident_criteria
    texts = [c.text for c in criteria if c.text]
    assert [t.section for t in texts] == [
        f"Reglamento Delegado (UE) 2024/1772, artículo {n}" for n in range(1, 10)
    ]
    major = texts[7]
    assert major.official_text_es.startswith(
        "1. Un incidente se considerará un incidente grave a efectos del artículo 19"
    )
    assert (major.official_text_en or "").startswith(
        "1. An incident shall be considered a major incident for the purposes of Article 19(1)"
    )


def test_dora_reporting_clocks_follow_delegated_regulation_2025_301() -> None:
    """Article 5(1) and 5(2) of 2025/301 (dora SOURCES.md): 4 h from classification as major and
    no later than 24 h from awareness (#224), then 72 h, then one month."""
    clocks = pack("dora").metadata.attributes.reporting_clocks
    assert [(c.key, c.hours, c.months, c.after, c.starts, c.outer_limit_hours) for c in clocks] == [
        ("initial_notification", 4, None, None, "classified", 24),
        ("intermediate_report", 72, None, "initial_notification", "aware", None),
        ("final_report", None, 1, "intermediate_report", "aware", None),
    ]
    assert all(c.needs == "significant" and c.requirement == "c3.art19" for c in clocks)
