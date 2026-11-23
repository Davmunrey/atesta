"""Preparation templates expose useful controls without invented normative coverage."""

import json
from pathlib import Path

from atesta_api.modules.compliance.catalog import read_catalog

ROOT = Path(__file__).resolve().parents[3]


def test_planned_templates_have_guides_but_no_assessable_requirements() -> None:
    expected = set()
    for provider in ("m365", "googleworkspace"):
        path = ROOT / "scanner/expected/5.49.0" / f"{provider}.json"
        expected.update(json.loads(path.read_text())[provider])
    catalog = read_catalog(ROOT / "catalog", expected_checks=expected, engine_version="5.49.0")
    packs = {p.metadata.id: p for p in catalog.packs}
    for key in ("iso27001_2022", "dora", "soc2"):
        pack = packs[key]
        assert pack.metadata.attributes.content_state == "template"
        assert pack.metadata.attributes.assessment_enabled is False
        assert pack.requirements == []
        assert pack.mappings == []
        guides = catalog.used_controls(pack)
        assert guides
        assert any(c.manual for c in guides)
        assert any(not c.manual for c in guides)
        assert all(c.description_es and c.description_en and c.remediation_refs for c in guides)
