"""Catalog boundaries: reject misleading or inconsistent preparation content."""

import copy
from datetime import date
from pathlib import Path

import pytest
import yaml


def catalog_files(root: Path) -> None:
    pack = root / "frameworks" / "sample"
    pack.mkdir(parents=True)
    controls = root / "controls"
    controls.mkdir()
    metadata = {
        "id": "sample",
        "name": "Sample draft",
        "version": "1",
        "jurisdiction": "test",
        "source": "https://example.test/standard",
        "license_notes": "Synthetic test content",
        "status": "draft",
        "attributes": {
            "content_state": "partial",
            "assessment_enabled": False,
            "summary_es": "Prueba",
            "summary_en": "Test",
            "scope_es": "Alcance de prueba",
            "scope_en": "Test scope",
            "applicability_es": "Requiere revisión",
            "applicability_en": "Review required",
            "limitations_es": "Sin evaluación",
            "limitations_en": "No assessment",
            "preparation_controls": ["ctl.review"],
            "source_refs": ["https://example.test/standard"],
            "verified_on": "2026-11-13",
        },
    }
    requirement = {
        "id": "R1",
        "title_es": "Texto de prueba",
        "title_en": "Test text",
        "applies_to": [],
        "source": "https://example.test/standard#r1",
        "attributes": {
            "official_text_es": "Texto sintético.",
            "applicability_es": "Aplicación sintética.",
            "selection_basis": "Dimension",
            "selection_rules": [{"level": "LOW", "rule": "R1 or R2"}],
            "section": "1",
            "source_sha256": "a" * 64,
        },
    }
    control = {
        "id": "ctl.review",
        "title_es": "Revisión",
        "title_en": "Review",
        "description_es": "Revisar la evidencia.",
        "description_en": "Review the evidence.",
        "manual": True,
        "prowler_checks": [],
        "atesta_checks": [],
        "remediation_refs": ["https://example.test/guide"],
    }
    mapping = {
        "requirement_id": "R1",
        "control_id": "ctl.review",
        "rationale": "Documentary review",
        "source": "https://example.test/standard#r1",
        "reviewed_by": None,
    }
    coverage = {
        "source": "Synthetic standard",
        "entries": [
            {"units": ["s1"], "status": "covered", "requirements": ["R1"]},
            {
                "units": ["s2"],
                "status": "excluded",
                "reason_es": "Glosario",
                "reason_en": "Glossary",
            },
        ],
    }
    for path, data in [
        (pack / "pack.yaml", metadata),
        (pack / "coverage.yaml", coverage),
        (pack / "requirements.yaml", {"requirements": [requirement]}),
        (pack / "mappings.yaml", {"mappings": [mapping]}),
        (controls / "review.yaml", control),
    ]:
        path.write_text(yaml.safe_dump(data, allow_unicode=True))


def read(root: Path):  # type: ignore[no-untyped-def]
    from atesta_api.modules.compliance.catalog import read_catalog

    return read_catalog(root, expected_checks={"known_check"}, engine_version="1")


def change(root: Path, name: str, update):  # type: ignore[no-untyped-def]
    path = root / name
    data = yaml.safe_load(path.read_text())
    update(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True))


def test_preview_preserves_alternative_rules_and_uses_content_hash(tmp_path: Path) -> None:
    catalog_files(tmp_path)
    first = read(tmp_path)
    requirement = first.packs[0].requirements[0]
    assert requirement.attributes.selection_rules[0].rule == "R1 or R2"
    assert first.packs[0].metadata.attributes.assessment_enabled is False
    assert first.fingerprint(first.packs[0]) == read(tmp_path).fingerprint(first.packs[0])
    change(
        tmp_path,
        "controls/review.yaml",
        lambda d: d.update(description_en="Review signed evidence."),
    )
    second = read(tmp_path)
    assert first.fingerprint(first.packs[0]) != second.fingerprint(second.packs[0])


@pytest.mark.parametrize(
    "case",
    [
        "duplicate",
        "dangling",
        "unknown_check",
        "manual_check",
        "unsafe_link",
        "scoring",
        "released",
        "candidate",
        "missing_source",
        "automated_only",
    ],
)
def test_invalid_content_cannot_enter_preview(tmp_path: Path, case: str) -> None:
    catalog_files(tmp_path)
    if case == "duplicate":
        change(
            tmp_path,
            "frameworks/sample/requirements.yaml",
            lambda d: d["requirements"].append(copy.deepcopy(d["requirements"][0])),
        )
    elif case == "dangling":
        change(
            tmp_path,
            "frameworks/sample/mappings.yaml",
            lambda d: d["mappings"][0].update(requirement_id="absent"),
        )
    elif case in {"unknown_check", "manual_check", "automated_only"}:
        change(
            tmp_path,
            "controls/review.yaml",
            lambda d: d.update(
                manual=case == "manual_check",
                prowler_checks=["absent" if case == "unknown_check" else "known_check"],
            ),
        )
    elif case == "unsafe_link":
        change(
            tmp_path,
            "controls/review.yaml",
            lambda d: d.update(remediation_refs=["javascript:alert(1)"]),
        )
    elif case == "scoring":
        change(
            tmp_path,
            "frameworks/sample/pack.yaml",
            lambda d: d["attributes"].update(assessment_enabled=True),
        )
    elif case == "released":
        change(tmp_path, "frameworks/sample/pack.yaml", lambda d: d.update(status="released"))
    elif case == "candidate":
        change(
            tmp_path,
            "frameworks/sample/pack.yaml",
            lambda d: d["attributes"].update(preparation_controls=["missing"]),
        )
    else:
        change(
            tmp_path,
            "frameworks/sample/mappings.yaml",
            lambda d: d["mappings"][0].update(source=""),
        )
    with pytest.raises(ValueError):
        read(tmp_path)


def test_duplicate_yaml_keys_are_not_silently_overwritten(tmp_path: Path) -> None:
    catalog_files(tmp_path)
    path = tmp_path / "frameworks/sample/pack.yaml"
    path.write_text(path.read_text() + "status: released\n")
    with pytest.raises(ValueError, match="duplicate"):
        read(tmp_path)


def test_every_scope_term_needs_readable_labels(tmp_path: Path) -> None:
    """i18n-complete spec: axes, dimension keys and levels read in ES and EN, not as bare codes."""
    catalog_files(tmp_path)
    change(
        tmp_path,
        "frameworks/sample/requirements.yaml",
        lambda d: d["requirements"][0]["attributes"].update(selection_basis="nivel · C"),
    )
    with pytest.raises(ValueError, match="readable labels"):
        read(tmp_path)
    labels = [{"term": t, "es": t, "en": t.lower()} for t in ("nivel", "C", "LOW")]
    change(
        tmp_path,
        "frameworks/sample/pack.yaml",
        lambda d: d["attributes"].update(term_labels=labels[:2]),
    )
    with pytest.raises(ValueError, match="readable labels"):
        read(tmp_path)
    change(
        tmp_path,
        "frameworks/sample/pack.yaml",
        lambda d: d["attributes"].update(term_labels=labels),
    )
    assert read(tmp_path).packs[0].metadata.attributes.term_labels[2].en == "low"


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("missing", "no coverage.yaml"),
        ("unknown", "unknown requirements"),
        ("uncovered", "outside any covered unit"),
        ("duplicate", "duplicate coverage unit"),
        ("unexplained", "reason in ES and EN"),
    ],
)
def test_every_requirement_sits_in_a_unit_of_the_source(
    tmp_path: Path, case: str, message: str
) -> None:
    """Content model v2: the coverage ledger accounts for the source and every requirement."""
    catalog_files(tmp_path)
    ledger = tmp_path / "frameworks/sample/coverage.yaml"
    if case == "missing":
        ledger.unlink()
    elif case == "unknown":
        change(
            tmp_path,
            "frameworks/sample/coverage.yaml",
            lambda d: d["entries"][0].update(requirements=["R1", "R9"]),
        )
    elif case == "uncovered":
        change(
            tmp_path,
            "frameworks/sample/coverage.yaml",
            lambda d: d["entries"][0].update(
                status="excluded", requirements=[], reason_es="x", reason_en="x"
            ),
        )
    elif case == "duplicate":
        change(
            tmp_path,
            "frameworks/sample/coverage.yaml",
            lambda d: d["entries"][1].update(units=["s1"]),
        )
    else:
        change(
            tmp_path, "frameworks/sample/coverage.yaml", lambda d: d["entries"][1].pop("reason_en")
        )
    with pytest.raises(ValueError, match=message):
        read(tmp_path)


CLOCK = {
    "key": "notice",
    "title_es": "Notificación",
    "title_en": "Notification",
    "hours": 72,
    "needs": "personal_data",
    "requirement": "R1",
}


@pytest.mark.parametrize(
    ("clocks", "message"),
    [
        ([{**CLOCK, "requirement": "R9"}], "unknown requirement"),
        ([CLOCK, CLOCK], "duplicate"),
        ([{**CLOCK, "after": "missing"}], "starts from an unknown clock"),
        ([{**CLOCK, "after": "notice"}], "starts from an unknown clock"),
        ([{**CLOCK, "months": 1}], "hours or months"),
        ([{k: v for k, v in CLOCK.items() if k != "hours"}], "hours or months"),
    ],
)
def test_reporting_clocks_are_checked_against_the_pack(
    tmp_path: Path, clocks: list[dict[str, object]], message: str
) -> None:
    """recorded-routines spec: clocks are pack content, tied to the pack's own requirements."""
    catalog_files(tmp_path)
    change(
        tmp_path,
        "frameworks/sample/pack.yaml",
        lambda d: d["attributes"].update(reporting_clocks=clocks),
    )
    with pytest.raises(ValueError, match=message):
        read(tmp_path)


def test_a_clock_may_start_from_an_earlier_clock(tmp_path: Path) -> None:
    catalog_files(tmp_path)
    final = {**CLOCK, "key": "final", "hours": None, "months": 1, "after": "notice"}
    change(
        tmp_path,
        "frameworks/sample/pack.yaml",
        lambda d: d["attributes"].update(reporting_clocks=[CLOCK, final]),
    )
    clocks = read(tmp_path).packs[0].metadata.attributes.reporting_clocks
    assert [(c.key, c.after, c.months) for c in clocks] == [
        ("notice", None, None),
        ("final", "notice", 1),
    ]


def test_incident_criteria_name_requirements_of_their_own_pack(tmp_path: Path) -> None:
    """recorded-routines spec: the text next to an incident flag is a requirement of the pack."""
    catalog_files(tmp_path)
    change(
        tmp_path,
        "frameworks/sample/pack.yaml",
        lambda d: d["attributes"].update(
            incident_criteria=[{"needs": "significant", "requirement": "R9"}]
        ),
    )
    with pytest.raises(ValueError, match="unknown requirement"):
        read(tmp_path)
    change(
        tmp_path,
        "frameworks/sample/pack.yaml",
        lambda d: d["attributes"].update(
            incident_criteria=[{"needs": "personal_data", "requirement": "R1"}]
        ),
    )
    criteria = read(tmp_path).packs[0].metadata.attributes.incident_criteria
    assert [(c.needs, c.requirement) for c in criteria] == [("personal_data", "R1")]


INLINE = {
    "needs": "significant",
    "text": {
        "section": "Artículo 3",
        "title_es": "Incidentes significativos",
        "title_en": "Significant incidents",
        "official_text_es": "Texto oficial.",
        "official_text_en": "Official text.",
        "source": "https://example.test/act#art_3",
        "source_sha256": "b" * 64,
    },
}


@pytest.mark.parametrize(
    ("criterion", "message"),
    [
        ({"needs": "significant"}, "requirement or an official text"),
        ({**INLINE, "requirement": "R1"}, "requirement or an official text"),
    ],
)
def test_an_incident_criterion_is_a_requirement_or_an_inline_official_text(
    tmp_path: Path, criterion: dict[str, object], message: str
) -> None:
    catalog_files(tmp_path)
    change(
        tmp_path,
        "frameworks/sample/pack.yaml",
        lambda d: d["attributes"].update(incident_criteria=[criterion]),
    )
    with pytest.raises(ValueError, match=message):
        read(tmp_path)
    change(
        tmp_path,
        "frameworks/sample/pack.yaml",
        lambda d: d["attributes"].update(incident_criteria=[INLINE]),
    )
    found = read(tmp_path).packs[0].metadata.attributes.incident_criteria[0]
    assert found.text is not None and found.text.section == "Artículo 3"


EXPECTED = {
    "reviewed_by": None,
    "items": [
        {
            "es": "Política aprobada y comunicada a la plantilla.",
            "en": "Approved policy, communicated to staff.",
            "ref": {"guide": "Synthetic guide", "edition": "2026-04", "section": "6.2", "page": 18},
        }
    ],
}


def test_a_requirement_may_list_the_evidence_a_guide_expects(tmp_path: Path) -> None:
    """requirement-register spec, expected evidence (#226): own words, cited, a candidate."""
    catalog_files(tmp_path)
    change(
        tmp_path,
        "frameworks/sample/requirements.yaml",
        lambda d: d["requirements"][0]["attributes"].update(expected_evidence=EXPECTED),
    )
    found = read(tmp_path).packs[0].requirements[0].attributes.expected_evidence
    assert found is not None and found.reviewed_by is None
    item = found.items[0]
    assert (item.es, item.ref.guide, item.ref.edition, item.ref.page) == (
        "Política aprobada y comunicada a la plantilla.",
        "Synthetic guide",
        "2026-04",
        18,
    )


def _item(**changes: object) -> dict[str, object]:
    return {**EXPECTED["items"][0], **changes}  # type: ignore[index]


def _ref(**changes: object) -> dict[str, object]:
    return {**EXPECTED["items"][0]["ref"], **changes}  # type: ignore[index]


@pytest.mark.parametrize(
    "block",
    [
        {**EXPECTED, "reviewed_by": "David Muñoz"},
        {**EXPECTED, "reviewed_on": "2026-11-23"},
        {**EXPECTED, "reviewed_by": " ", "reviewed_on": "2026-11-23"},
        {**EXPECTED, "reviewed_by": "David Muñoz", "reviewed_on": "23/11/2026"},
        {"items": EXPECTED["items"]},
        {**EXPECTED, "items": []},
        {**EXPECTED, "items": [_item()] * 9},
        {**EXPECTED, "items": [_item(en="")]},
        {**EXPECTED, "items": [{k: v for k, v in _item().items() if k != "es"}]},
        {**EXPECTED, "items": [_item(es="x" * 201)]},
        {**EXPECTED, "items": [_item(ref=_ref(page=0))]},
        {**EXPECTED, "items": [_item(ref=_ref(edition="abril 2026"))]},
        {**EXPECTED, "items": [_item(ref=_ref(section=" "))]},
        {**EXPECTED, "items": [_item(note="copied text")]},
    ],
    ids=[
        "signer_without_date",
        "date_without_signer",
        "blank_signer",
        "date_not_iso",
        "no_marker",
        "empty",
        "too_long_list",
        "no_en",
        "no_es",
        "long_item",
        "page_zero",
        "edition_text",
        "no_section",
        "extra_field",
    ],
)
def test_expected_evidence_must_be_cited_short_and_signed_in_full(
    tmp_path: Path, block: dict[str, object]
) -> None:
    catalog_files(tmp_path)
    change(
        tmp_path,
        "frameworks/sample/requirements.yaml",
        lambda d: d["requirements"][0]["attributes"].update(expected_evidence=block),
    )
    with pytest.raises(ValueError):
        read(tmp_path)


def test_the_owner_signs_expected_evidence_with_a_name_and_a_date(tmp_path: Path) -> None:
    """A signature adds two fields and changes nothing else in the content (owner, 2026-11-23)."""
    catalog_files(tmp_path)
    signed = {**EXPECTED, "reviewed_by": "David Muñoz", "reviewed_on": "2026-11-23"}
    change(
        tmp_path,
        "frameworks/sample/requirements.yaml",
        lambda d: d["requirements"][0]["attributes"].update(expected_evidence=signed),
    )
    found = read(tmp_path).packs[0].requirements[0].attributes.expected_evidence
    assert found is not None
    assert (found.reviewed_by, found.reviewed_on) == ("David Muñoz", date(2026, 11, 23))


# --- scope profiles (requirement-register spec, issue 227) ----------------------------------

REF = {"guide": "Guía sintética", "edition": "2026-11", "section": "4", "page": 8}
PROFILE = {
    "key": "small_it",
    "title_es": "Perfil sintético",
    "title_en": "Synthetic profile",
    "summary_es": "Resumen propio.",
    "summary_en": "Own summary.",
    "refs": [REF],
    "levels": {"R1": "BAJO"},
    "criteria": {"R1": {"section": "5.1", "page": 12}},
    "reviewed_by": None,
}


def test_a_pack_may_publish_a_scope_profile(tmp_path: Path) -> None:
    catalog_files(tmp_path)
    change(
        tmp_path,
        "frameworks/sample/pack.yaml",
        lambda d: d["attributes"].update(scope_profiles=[PROFILE]),
    )
    [profile] = read(tmp_path).packs[0].metadata.attributes.scope_profiles
    assert (profile.key, profile.levels, profile.reviewed_by) == ("small_it", {"R1": "BAJO"}, None)
    assert profile.criteria["R1"].page == 12


@pytest.mark.parametrize(
    ("profiles", "message"),
    [
        ([{**PROFILE, "levels": {}}], "every requirement"),
        ([{**PROFILE, "levels": {"R1": "BAJO", "R9": "n.a."}}], "every requirement"),
        ([{**PROFILE, "criteria": {"R9": {"section": "5", "page": 1}}}], "criteria"),
        ([PROFILE, PROFILE], "duplicate scope profile"),
        ([{**PROFILE, "reviewed_on": "2026-11-23"}], "reviewer and the review date"),
        ([{**PROFILE, "refs": []}], "refs"),
        ([{**PROFILE, "key": "profile"}], "reserved"),
    ],
)
def test_scope_profiles_are_checked_against_the_pack(
    tmp_path: Path, profiles: list[dict[str, object]], message: str
) -> None:
    catalog_files(tmp_path)
    change(
        tmp_path,
        "frameworks/sample/pack.yaml",
        lambda d: d["attributes"].update(scope_profiles=profiles),
    )
    with pytest.raises(ValueError, match=message):
        read(tmp_path)
