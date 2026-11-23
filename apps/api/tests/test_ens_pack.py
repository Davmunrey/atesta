"""Independent Annex II examples and partial-mapping behavior from the official source."""

import json
from datetime import date
from pathlib import Path

from atesta_api.modules.compliance.catalog import Catalog, read_catalog
from atesta_core.frameworks import Mapping, framework_results
from atesta_core.scoring import ControlResult, Status

ROOT = Path(__file__).resolve().parents[3]


def _catalog() -> Catalog:
    expected: set[str] = set()
    for provider in ("m365", "googleworkspace"):
        expected.update(
            json.loads((ROOT / "scanner/expected/5.52.0" / f"{provider}.json").read_text())[
                provider
            ]
        )
    return read_catalog(ROOT / "catalog", expected_checks=expected, engine_version="5.52.0")


def test_ens_preserves_dimension_levels_and_alternative_reinforcements() -> None:
    expected = set()
    for provider in ("m365", "googleworkspace"):
        expected.update(
            json.loads((ROOT / "scanner/expected/5.52.0" / f"{provider}.json").read_text())[
                provider
            ]
        )
    catalog = read_catalog(ROOT / "catalog", expected_checks=expected, engine_version="5.52.0")
    pack = next(p for p in catalog.packs if p.metadata.id == "ens_rd311_2022")
    requirements = {r.id: r for r in pack.requirements}
    assert len(requirements) == 73
    internal = requirements["op.acc.6"].attributes
    assert internal.selection_basis == "nivel · C I T A"
    assert internal.selection_rules[0].rule == "+ [R1 o R2 o R3 o R4] + R8 + R9"
    assert "zonas no controladas" in internal.official_text_es
    assert requirements["op.acc.3"].attributes.selection_rules[0].rule == "n.a."
    cloud = requirements["op.nub.1"].attributes
    assert cloud.selection_basis == "categoría · Todas"
    assert cloud.selection_rules[0].level == "BÁSICA"
    assert cloud.selection_rules[2].rule == "+R1+R2"
    assert requirements["mp.info.6"].attributes.selection_rules[0].level == "BAJO"
    assert "Nivel ALTO" in requirements["mp.info.6"].attributes.applicability_es
    assert "op.exp.4" in requirements["op.exp.4"].attributes.applicability_es
    assert pack.metadata.attributes.assessment_enabled is False
    assert all(
        m.reviewed_by in (None, "David Muñoz") for m in pack.mappings
    )  # signed: test_mapping_signoffs
    mappings = [Mapping(pack.metadata.id, m.requirement_id, m.control_id) for m in pack.mappings]
    passing_checks = [
        ControlResult(c.id, Status.PASS) for c in catalog.controls.values() if not c.manual
    ]
    results = framework_results(pack.metadata.id, requirements, mappings, passing_checks)
    assert len(results) == 73
    assert {r.status for r in results} == {Status.MANUAL}
    assert {m.requirement_id for m in pack.mappings} == requirements.keys()


def test_every_requirement_group_has_its_official_heading() -> None:
    """A pack that declares group headings covers every code prefix (workspace-ux spec)."""
    expected: set[str] = set()
    for provider in ("m365", "googleworkspace"):
        expected.update(
            json.loads((ROOT / "scanner/expected/5.52.0" / f"{provider}.json").read_text())[
                provider
            ]
        )
    catalog = read_catalog(ROOT / "catalog", expected_checks=expected, engine_version="5.52.0")
    for pack in catalog.packs:
        titles = {g.prefix: g.title for g in pack.metadata.attributes.groups_es}
        if not titles:
            continue
        prefixes = {r.id.rsplit(".", 1)[0] for r in pack.requirements}
        assert prefixes <= titles.keys(), (pack.metadata.id, sorted(prefixes - titles.keys()))
    ens = next(p for p in catalog.packs if p.metadata.id == "ens_rd311_2022")
    # Copied from the BOE text (catalog/frameworks/ens_rd311_2022/SOURCES.md, Group headings).
    groups = [g.prefix for g in ens.metadata.attributes.groups_es]
    titles = {g.prefix: g.title for g in ens.metadata.attributes.groups_es}
    assert titles["op.acc"] == "Control de acceso"
    assert titles["mp.eq"] == "Protección de los equipos"
    # The BOE's order: organizational, then operational, then protective measures.
    assert (
        groups.index("org") < groups.index("op.pl") < groups.index("op.mon") < groups.index("mp.if")
    )


def test_mp_s_2_keeps_the_space_inside_the_italic_web() -> None:
    """The BOE prints `servicios <em>web </em>deberán`: the space sits inside the italics, and
    stripping the tag must not drop it (original HTML, SHA-256 6249bcb3…, SOURCES.md)."""
    pack = next(p for p in _catalog().packs if p.metadata.id == "ens_rd311_2022")
    text = next(r for r in pack.requirements if r.id == "mp.s.2").attributes.official_text_es
    assert "Los sistemas que prestan servicios web deberán ser protegidos" in text
    assert "webdeberán" not in text


# The owner signed the expected evidence of all 73 measures in session on 2026-11-23, in four
# family blocks, after the 808 page references were checked (author 248/248, coordinator 12/12).
SIGNED_BY, SIGNED_ON = "David Muñoz", date(2026, 11, 23)

SUBSECTIONS = {
    "org": "6.2.1",
    "op.pl": "6.2.2.1",
    "op.acc": "6.2.2.2",
    "op.exp": "6.2.2.3",
    "op.ext": "6.2.2.4",
    "op.nub": "6.2.2.5",
    "op.cont": "6.2.2.6",
    "op.mon": "6.2.2.7",
    "mp.if": "6.2.3.1",
    "mp.per": "6.2.3.2",
    "mp.eq": "6.2.3.3",
    "mp.com": "6.2.3.4",
    "mp.si": "6.2.3.5",
    "mp.sw": "6.2.3.6",
    "mp.info": "6.2.3.7",
    "mp.s": "6.2.3.8",
}


def test_every_ens_measure_lists_the_evidence_ccn_stic_808_proposes() -> None:
    """requirement-register spec (#226): a candidate checklist for each Annex II measure, in
    Atesta's words, citing the CCN-STIC 808 (April 2026) subsection, the measure and the printed
    page of its evidence proposal (body pages 18 to 105, where printed page = PDF page)."""
    pack = next(p for p in _catalog().packs if p.metadata.id == "ens_rd311_2022")
    signed = set()
    for requirement in pack.requirements:
        block = requirement.attributes.expected_evidence
        assert block is not None, requirement.id
        if (block.reviewed_by, block.reviewed_on) == (SIGNED_BY, SIGNED_ON):
            signed.add(requirement.id)
        group = requirement.id.rsplit(".", 1)[0]  # org.1 -> org, op.acc.1 -> op.acc
        for item in block.items:
            assert (item.ref.guide, item.ref.edition) == ("CCN-STIC 808", "2026-04")
            assert item.ref.section == f"{SUBSECTIONS[group]} ({requirement.id})"
            assert 18 <= item.ref.page <= 105, requirement.id
            assert item.es != item.en
    assert signed == {r.id for r in pack.requirements}
    # Spot checks re-opened in the PDF (pull request for #226 lists them).
    pages = {r.id: r.attributes.expected_evidence.items[0].ref.page for r in pack.requirements}  # type: ignore[union-attr]
    assert (pages["org.1"], pages["op.pl.1"], pages["op.exp.6"], pages["mp.if.4"]) == (
        18,
        24,
        50,
        71,
    )
    assert (pages["mp.per.2"], pages["mp.info.6"], pages["mp.s.4"]) == (76, 99, 104)


def test_ens_offers_the_ccn_stic_890c_profiles_as_scope_options() -> None:
    """requirement-register spec, issue 227: 890C section 4 (pages 8-10), totals in 4.1."""
    ens = next(p for p in _catalog().packs if p.metadata.id == "ens_rd311_2022")
    codes = {r.id for r in ens.requirements}
    profiles = {p.key: p for p in ens.metadata.attributes.scope_profiles}
    assert set(profiles) == {"pce_rfs_small_it", "pce_rfs_small_it_ot_iot"}
    applying = {}
    for key, profile in profiles.items():
        assert set(profile.levels) == codes and len(codes) == 73
        applying[key] = {c for c, v in profile.levels.items() if v != "n.a."}
        # Signed by the owner on 2026-11-23; the 73 IT values were checked against §4 (73/73).
        assert (profile.reviewed_by, profile.reviewed_on) == (SIGNED_BY, SIGNED_ON)
        assert (profile.refs[0].guide, profile.refs[0].section, profile.refs[0].page) == (
            "CCN-STIC 890C",
            "4",
            8,
        )
        for conditional, section in (
            ("op.exp.9", "5.7"),
            ("op.ext.3", "5.8"),
            ("op.cont.2", "5.9"),
        ):
            assert profile.levels[conditional] == "n.a."
            assert profile.criteria[conditional].section == section
    assert (len(applying["pce_rfs_small_it"]), len(applying["pce_rfs_small_it_ot_iot"])) == (38, 42)
    assert applying["pce_rfs_small_it_ot_iot"] - applying["pce_rfs_small_it"] == {
        "op.exp.5",
        "op.mon.1",
        "mp.if.2",
        "mp.com.4",
    }
    assert profiles["pce_rfs_small_it"].levels["mp.eq.2"] == "MEDIO"


def test_ens_guides_the_scope_with_the_ccn_stic_803_valuation_order() -> None:
    """requirement-register spec, issue 225: information (C, I, T, A), then services (D)."""
    ens = next(p for p in _catalog().packs if p.metadata.id == "ens_rd311_2022")
    guide = ens.metadata.attributes.scope_guide
    assert guide is not None and (guide.reviewed_by, guide.reviewed_on) == (SIGNED_BY, SIGNED_ON)
    assert [(s.asset, s.key) for s in guide.steps] == [
        ("information", "C"),
        ("information", "I"),
        ("information", "T"),
        ("information", "A"),
        ("service", "D"),
    ]
    assert guide.category_by_level == {"BAJO": "BÁSICA", "MEDIO": "MEDIA", "ALTO": "ALTA"}
    refs = {(r.ref.guide, r.ref.edition, r.ref.section, r.ref.page) for r in guide.notes}
    assert ("CCN-STIC 803", "2025-06", "4.1", 12) in refs
    assert ("CCN-STIC 803", "2025-06", "4.5", 15) in refs
