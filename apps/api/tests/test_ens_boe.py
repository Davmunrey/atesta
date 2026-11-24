"""ENS source records (issue 277): every source_sha256 is recomputable, and the pack's Spanish
text cannot drift from the BOE record it was copied from (rule 10)."""

import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/api, as test_eu_act does
ens_boe: Any = importlib.import_module("devtools.ens_boe")

PACK = Path(__file__).resolve().parents[3] / "catalog/frameworks/ens_rd311_2022"
REQUIREMENTS = yaml.safe_load((PACK / "requirements.yaml").read_text(encoding="utf-8"))[
    "requirements"
]
STORED = json.loads((PACK / "source_records.json").read_text(encoding="utf-8"))
RECORDS = {record["id"]: record for record in STORED["records"]}

PAGE = """<html><body>
<p class="parrafo">Texto anterior al anexo, fuera de toda medida.</p>
<p class="centro_cursiva">4. Marco operacional [op]</p>
<p class="parrafo_2">4.1 Planificación [op.pl].</p>
<p class="parrafo_2">4.1.1 Análisis de&nbsp;riesgos [op.pl.1].</p>
<table class="tabla"><tbody>
<tr><td>dimensiones</td><td colspan="3">Todas</td></tr>
<tr><td>categoría</td><td>BÁSICA</td><td>MEDIA</td><td>ALTA</td></tr>
<tr><td>&nbsp;</td><td><p>aplica</p></td><td>
   <p>+ R1</p>
 </td><td><p>+ R2</p></td></tr>
</tbody></table>
<p class="parrafo_2">Requisitos.</p>
<p class="parrafo_2">–&ensp;[op.pl.1.1] Los servicios <em>web </em>deberán   protegerse
   &laquo;siempre&raquo;.</p>
<p class="imagen">
  <img src="/x.png" alt="Imagen: /x.png"/>
</p>
<p class="parrafo_2">Aplicación de la medida.</p>
<p class="parrafo_2">– Categoría BÁSICA: op.pl.1.</p>
<p class="parrafo_2">4.2 Control de acceso [op.acc].</p>
<p class="parrafo_2">El control de acceso no pertenece a op.pl.1.</p>
<p class="parrafo_2">4.2.1 Identificación [op.acc.1].</p>
<p class="parrafo_2">1. Una lista numerada no cierra la medida.</p>
<p class="centro_cursiva">6. Valoración de la implantación</p>
<p class="parrafo">Esto tampoco pertenece a ninguna medida.</p>
</body></html>"""


def test_a_measure_is_its_heading_its_tables_and_its_paragraphs() -> None:
    first, second = ens_boe.records(PAGE)
    assert first == {
        "id": "op.pl.1",
        "title_es": "Análisis de riesgos",
        "section": "4.1.1",
        "paragraphs": [
            "Requisitos.",
            # Entities decoded, runs of any whitespace are one space, and the text inside an
            # inline element is trimmed before it joins: the artifact behind mp.s.2 (issue 249).
            "– [op.pl.1.1] Los servicios webdeberán protegerse «siempre».",
            "Aplicación de la medida.",
            "– Categoría BÁSICA: op.pl.1.",
        ],
        "tables": [
            [
                ["dimensiones", "Todas"],
                ["categoría", "BÁSICA", "MEDIA", "ALTA"],
                ["", "aplica", "+ R1", "+ R2"],
            ]
        ],
    }
    assert second == {
        "id": "op.acc.1",
        "title_es": "Identificación",
        "section": "4.2.1",
        "paragraphs": ["1. Una lista numerada no cierra la medida."],
        "tables": [],
    }


def test_the_hash_is_the_documented_serialization() -> None:
    record = {"id": "x", "title_es": "ñ", "section": "1.1", "paragraphs": ["a"], "tables": []}
    text = '{"id": "x", "paragraphs": ["a"], "section": "1.1", "tables": [], "title_es": "ñ"}'
    assert ens_boe.record_sha256(record) == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_any_file_but_the_pinned_capture_is_refused(tmp_path: Path) -> None:
    other = tmp_path / "boe.html"
    other.write_text(PAGE, encoding="utf-8")
    with pytest.raises(ValueError, match="not the pinned capture"):
        ens_boe.read_pinned(other)
    assert ens_boe.PINNED_SHA256 in (PACK / "SOURCES.md").read_text(encoding="utf-8")
    assert STORED["source_sha256"] == ens_boe.PINNED_SHA256


def test_every_requirement_has_one_record_in_the_same_order() -> None:
    assert [r["id"] for r in REQUIREMENTS] == [r["id"] for r in STORED["records"]]
    assert len(RECORDS) == 73


@pytest.mark.parametrize("requirement", REQUIREMENTS, ids=lambda r: r["id"])
def test_source_sha256_is_the_hash_of_the_record(requirement: dict[str, Any]) -> None:
    record = RECORDS[requirement["id"]]
    assert ens_boe.record_sha256(record) == requirement["attributes"]["source_sha256"]


@pytest.mark.parametrize("requirement", REQUIREMENTS, ids=lambda r: r["id"])
def test_the_pack_text_is_the_record_text(requirement: dict[str, Any]) -> None:
    """A correction like issue 249 must be written down in CORRECTIONS, not slipped in."""
    derived = ens_boe.derive(RECORDS[requirement["id"]])
    attributes = requirement["attributes"]
    assert requirement["title_es"] == derived["title_es"]
    assert str(attributes["section"]) == derived["section"]
    assert attributes["official_text_es"] == derived["official_text_es"]
    assert attributes["applicability_es"] == derived["applicability_es"]
    assert attributes["selection_basis"] == derived["selection_basis"]
    assert attributes["selection_rules"] == derived["selection_rules"]


def test_every_listed_correction_is_still_needed() -> None:
    assert set(ens_boe.CORRECTIONS) <= set(RECORDS)
    for measure, pairs in ens_boe.CORRECTIONS.items():
        text = "\n".join(RECORDS[measure]["paragraphs"])
        for wrong, right in pairs:
            assert wrong in text and right not in text, (measure, wrong)
