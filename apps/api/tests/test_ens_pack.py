"""Independent Annex II examples and partial-mapping behavior from the official source."""

import json
from pathlib import Path

from atesta_api.modules.compliance.catalog import read_catalog
from atesta_core.frameworks import Mapping, framework_results
from atesta_core.scoring import ControlResult, Status

ROOT = Path(__file__).resolve().parents[3]


def test_ens_preserves_dimension_levels_and_alternative_reinforcements() -> None:
    expected = set()
    for provider in ("m365", "googleworkspace"):
        expected.update(
            json.loads((ROOT / "scanner/expected/5.49.0" / f"{provider}.json").read_text())[
                provider
            ]
        )
    catalog = read_catalog(ROOT / "catalog", expected_checks=expected, engine_version="5.49.0")
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
    assert all(m.reviewed_by is None for m in pack.mappings)
    mappings = [Mapping(pack.metadata.id, m.requirement_id, m.control_id) for m in pack.mappings]
    passing_checks = [
        ControlResult(c.id, Status.PASS) for c in catalog.controls.values() if not c.manual
    ]
    results = framework_results(pack.metadata.id, requirements, mappings, passing_checks)
    assert len(results) == 73
    assert {r.status for r in results} == {Status.MANUAL}
    assert {m.requirement_id for m in pack.mappings} == requirements.keys()
