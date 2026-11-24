"""National transposition record (nis2-transposition spec, #437): the notified measures of all 27
Member States, from the Publications Office, unsigned until the owner reviews them."""

import copy
import importlib
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from atesta_api.modules.compliance.catalog_schema import EU_MEMBER_STATES, Transposition
from test_catalog_content import catalog_files, change, read
from test_source_coverage import pack

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/api, as test_eu_act does
eu_nim: Any = importlib.import_module("devtools.eu_nim")

ACT = "32099L0001"
MEASURE = {
    "celex": f"7{ACT[1:]}AUT_1",
    "title": "Bundesgesetz (synthetisch)",
    "act_type": "Bundesgesetz",
    "reference": "BGBl. I Nr. 1/2099",
    "date": "2099-01-02",
    "notified_on": "2099-01-03",
    "url": "https://example.test/aut/1",
    "declaration": None,
}


def record() -> dict[str, Any]:
    states = [
        {"country": c, "status": "none_notified", "measures": []} for c in sorted(EU_MEMBER_STATES)
    ]
    states[0] = {"country": "AUT", "status": "notified", "measures": [dict(MEASURE)]}
    return {
        "act": ACT,
        "source": "https://example.test/sparql",
        "listing": f"https://example.test/nim/{ACT}",
        "relation": "http://example.test/ontology#implements",
        "pulled_on": "2099-01-10",
        "reviewed_by": None,
        "reviewed_on": None,
        "member_states": states,
        "national_context": [
            {
                "country": "ESP",
                "checked_on": "2099-01-10",
                "sources": ["https://example.test/boe"],
                "summary_es": "Ninguna medida notificada.",
                "summary_en": "No measure notified.",
                "references": [
                    {
                        "id": "BOE-A-2099-1",
                        "title": "Real Decreto sintético",
                        "url": "https://example.test/boe/1",
                        "section": "Artículo 1",
                        "quote_es": "Texto sintético.",
                    }
                ],
                "authorities": [],
            }
        ],
    }


def test_a_complete_unsigned_record_is_valid() -> None:
    parsed = Transposition.model_validate(record())
    assert len(parsed.member_states) == 27
    assert parsed.reviewed_by is None


def _drop_spain(d: dict[str, Any]) -> None:
    d["member_states"] = [s for s in d["member_states"] if s["country"] != "ESP"]


def _twice(d: dict[str, Any]) -> None:
    d["member_states"][-1] = copy.deepcopy(d["member_states"][0])


def _outsider(d: dict[str, Any]) -> None:
    d["member_states"][-1]["country"] = "GBR"


def _empty_notified(d: dict[str, Any]) -> None:
    d["member_states"][0]["measures"] = []


def _none_with_measures(d: dict[str, Any]) -> None:
    d["member_states"][1]["measures"] = [dict(MEASURE)]


def _plain_link(d: dict[str, Any]) -> None:
    d["member_states"][0]["measures"][0]["url"] = "http://example.test/aut/1"


def _no_date(d: dict[str, Any]) -> None:
    d["member_states"][0]["measures"][0].pop("notified_on")


def _late(d: dict[str, Any]) -> None:
    d["member_states"][0]["measures"][0]["notified_on"] = "2099-02-01"


def _context_outside(d: dict[str, Any]) -> None:
    d["national_context"][0]["country"] = "GBR"


def _context_twice(d: dict[str, Any]) -> None:
    d["national_context"].append(copy.deepcopy(d["national_context"][0]))


def _context_unsourced(d: dict[str, Any]) -> None:
    d["national_context"][0]["sources"] = []


def _authority_unsourced(d: dict[str, Any]) -> None:
    d["national_context"][0]["authorities"] = [{"name": "CSIRT", "role": "CSIRT"}]


def _half_signed(d: dict[str, Any]) -> None:
    d["reviewed_by"] = "Reviewer"


def _date_only(d: dict[str, Any]) -> None:
    d["reviewed_on"] = "2099-01-11"


@pytest.mark.parametrize(
    ("update", "message"),
    [
        (_drop_spain, "27 Member States"),
        (_twice, "27 Member States"),
        (_outsider, "27 Member States"),
        (_empty_notified, "notified status lists its measures"),
        (_none_with_measures, "notified status lists its measures"),
        (_plain_link, "HTTPS"),
        (_no_date, "notified_on"),
        (_late, "after the pull"),
        (_context_outside, "national context"),
        (_context_twice, "national context"),
        (_context_unsourced, "sources"),
        (_authority_unsourced, "source"),
        (_half_signed, "reviewer and the review date"),
        (_date_only, "reviewer and the review date"),
    ],
)
def test_the_schema_refuses_an_unsourced_or_incomplete_record(
    update: Callable[[dict[str, Any]], None], message: str
) -> None:
    data = record()
    update(data)
    with pytest.raises(ValueError, match=message):
        Transposition.model_validate(data)


def test_the_loader_reads_the_record_and_checks_its_act(tmp_path: Path) -> None:
    catalog_files(tmp_path)
    change(
        tmp_path,
        "frameworks/sample/pack.yaml",
        lambda d: d.update(source=f"https://example.test/celex/{ACT}"),
    )
    path = tmp_path / "frameworks/sample/transposition.yaml"
    path.write_text(yaml.safe_dump(record(), allow_unicode=True))
    loaded = read(tmp_path).packs[0].transposition
    assert loaded is not None
    assert loaded.member_states[0].measures[0].date == date(2099, 1, 2)
    change(tmp_path, "frameworks/sample/transposition.yaml", lambda d: d.update(act="32099L0002"))
    with pytest.raises(ValueError, match="act named in the pack's source"):
        read(tmp_path)


def test_a_pack_without_a_record_has_none(tmp_path: Path) -> None:
    catalog_files(tmp_path)
    assert read(tmp_path).packs[0].transposition is None


# The devtool turns one SPARQL response into member_states.


def _binding(country: str, celex: str, notified: str, **extra: str) -> dict[str, Any]:
    values = {
        "country": f"http://publications.europa.eu/resource/authority/country/{country}",
        "celex": celex,
        "title": f"Title {celex}",
        "date": "2024-01-01",
        "notified": notified,
        **extra,
    }
    return {k: {"value": v} for k, v in values.items()}


def test_the_devtool_lists_every_member_state_and_prefers_the_national_link() -> None:
    bindings = [
        _binding("AUT", "72022L2555AUT_2", "2025-02-01", link="https://ris.example.test/2"),
        _binding("AUT", "72022L2555AUT_1", "2025-01-01", link="http://insecure.example.test"),
        _binding("BEL", "72022L2555BEL_1", "2025-03-01", decl="CODE", type="Loi", ref="2024/1"),
    ]
    states = eu_nim.member_states(bindings)
    assert [s["country"] for s in states] == sorted(EU_MEMBER_STATES)
    austria = states[0]["measures"]
    assert [m["celex"] for m in austria] == ["72022L2555AUT_1", "72022L2555AUT_2"]
    assert austria[0]["url"] == "https://publications.europa.eu/resource/celex/72022L2555AUT_1"
    assert austria[1]["url"] == "https://ris.example.test/2"
    belgium = states[1]["measures"][0]
    assert (belgium["act_type"], belgium["reference"], belgium["declaration"]) == (
        "Loi",
        "2024/1",
        "CODE",
    )
    assert states[2] == {"country": "BGR", "status": "none_notified", "measures": []}
    Transposition.model_validate(
        {**record(), "pulled_on": "2026-01-01", "member_states": states, "national_context": []}
    )


def test_the_devtool_query_names_the_act() -> None:
    assert "resource/celex/32022L2555>" in eu_nim.query("32022L2555")
    with pytest.raises(ValueError, match="CELEX"):
        eu_nim.query('32022L2555> . } DROP {"')


# The NIS2 record in the repository.


def test_the_nis2_record_lists_the_27_member_states_with_sources_and_dates() -> None:
    nis2 = pack("nis2").transposition
    assert nis2 is not None
    assert nis2.act == "32022L2555"
    assert nis2.pulled_on == date(2026, 11, 24)
    assert str(nis2.source) == "https://publications.europa.eu/webapi/rdf/sparql"
    assert [s.country for s in nis2.member_states] == sorted(EU_MEMBER_STATES)
    measures = [m for s in nis2.member_states for m in s.measures]
    assert len(measures) == 305  # SOURCES.md: the 2026-11-24 pull
    assert all(m.url.startswith("https://") and m.date and m.notified_on for m in measures)
    assert all(
        m.celex.startswith("72022L2555" + s.country) for s in nis2.member_states for m in s.measures
    )


def test_the_nis2_record_is_unsigned() -> None:
    nis2 = pack("nis2").transposition
    assert nis2 is not None
    assert nis2.reviewed_by is None and nis2.reviewed_on is None


def test_spain_has_no_notified_measure_and_quotes_the_boe_verbatim() -> None:
    nis2 = pack("nis2").transposition
    assert nis2 is not None
    spain = next(s for s in nis2.member_states if s.country == "ESP")
    assert spain.status == "none_notified"
    context = next(c for c in nis2.national_context if c.country == "ESP")
    assert context.authorities == []
    assert {r.id for r in context.references} == {
        "BOE-A-2024-8715",
        "BOE-A-2025-16214",
        "BOE-A-2026-16757",
    }
    rd = next(r for r in context.references if r.id == "BOE-A-2024-8715")
    assert rd.quote_es.startswith("1. La notificación de incidentes será llevada a cabo")
    assert "fruto de la transposición de la Directiva (UE) 2022/2555" in rd.quote_es
    assert all(r.url.startswith("https://www.boe.es/") for r in context.references)
