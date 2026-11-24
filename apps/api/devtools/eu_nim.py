"""List the national measures each Member State notified for an EU directive (outside CI).

    uv run python -m apps.api.devtools.eu_nim 32022L2555 > members.yaml

Queries the EU Publications Office SPARQL endpoint for the measures linked to the act by
`cdm:measure_national_implementing_implements_resource_legal`, and prints `member_states` for
the 27 Member States as a transposition record expects it (transposition spec, #437). A country
without a measure is `none_notified`. Titles, types, references and declaration codes are
copied as published. The SHA-256 of the response goes to stderr for the pack's SOURCES.md.
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from typing import Any

import yaml
from atesta_api.modules.compliance.catalog_schema import EU_MEMBER_STATES

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
_CELEX = re.compile(r"^[0-9]{5}[A-Z][0-9]{4}$")
_OPTIONAL = {"type": "act_type", "ref": "reference", "decl": "declaration"}


def query(celex: str) -> str:
    if not _CELEX.match(celex):
        raise ValueError("expected a CELEX number such as 32022L2555")
    return f"""PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT ?country ?celex ?title ?type ?date ?notified ?ref ?link ?decl WHERE {{
  ?w owl:sameAs <http://publications.europa.eu/resource/celex/{celex}> .
  ?m cdm:measure_national_implementing_implements_resource_legal ?w ;
     cdm:measure_national_implementing_implemented_by_country ?country ;
     cdm:resource_legal_id_celex ?celex ;
     cdm:work_title ?title ;
     cdm:work_date_document ?date ;
     cdm:measure_national_implementing_date_notification ?notified .
  FILTER(STRSTARTS(STR(?celex), "7{celex[1:]}"))
  OPTIONAL {{ ?m cdm:measure_national_implementing_type_act ?type }}
  OPTIONAL {{ ?m cdm:measure_national_implementing_reference_member-state ?ref }}
  OPTIONAL {{ ?m cdm:measure_national_implementing_national_website_link ?link }}
  OPTIONAL {{ ?m cdm:measure_national_implementing_declaration_transposition_member-state ?decl }}
}}
ORDER BY ?country ?celex"""


def _measure(row: dict[str, str]) -> dict[str, Any]:
    link = row.get("link", "")
    plain = link.startswith("https://") and " " not in link
    measure: dict[str, Any] = {
        "celex": row["celex"],
        "title": " ".join(row["title"].split()),
        "date": row["date"],
        "notified_on": row["notified"],
        "url": link if plain else f"https://publications.europa.eu/resource/celex/{row['celex']}",
    }
    for key, field in _OPTIONAL.items():
        measure[field] = row[key].strip() if row.get(key, "").strip() else None
    return measure


def member_states(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per Member State, measures by notification date then CELEX."""
    found: dict[str, dict[str, dict[str, Any]]] = {c: {} for c in EU_MEMBER_STATES}
    for binding in bindings:
        row = {k: str(v["value"]) for k, v in binding.items()}
        country = row["country"].rsplit("/", 1)[-1]
        found[country].setdefault(row["celex"], _measure(row))
    states = []
    for country in sorted(found):
        measures = sorted(found[country].values(), key=lambda m: (m["notified_on"], m["celex"]))
        status = "notified" if measures else "none_notified"
        states.append({"country": country, "status": status, "measures": measures})
    return states


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("celex")
    args = parser.parse_args()
    url = f"{ENDPOINT}?{urllib.parse.urlencode({'query': query(args.celex)})}"
    accept = {"Accept": "application/sparql-results+json"}
    request = urllib.request.Request(url, headers=accept)  # noqa: S310 - fixed HTTPS endpoint
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - same
        body = response.read()
    print(f"sha256 {hashlib.sha256(body).hexdigest()}", file=sys.stderr)
    states = member_states(json.loads(body)["results"]["bindings"])
    yaml.safe_dump({"member_states": states}, sys.stdout, allow_unicode=True, sort_keys=False)


if __name__ == "__main__":
    main()
