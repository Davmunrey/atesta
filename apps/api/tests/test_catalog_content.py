"""Catalog boundaries: reject misleading or inconsistent preparation content."""

import copy
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
    for path, data in [
        (pack / "pack.yaml", metadata),
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
