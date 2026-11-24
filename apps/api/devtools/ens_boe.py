"""Rebuild the ENS source records from the BOE publication of RD 311/2022 (issue 277).

Each ENS requirement carries `source_sha256`: the hash of the record this module builds for its
Annex II measure. Capture the page outside CI, then check or rewrite the committed records:

    curl -sSL -o boe-a-2022-7191.html "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2022-7191"
    uv run python -m apps.api.devtools.ens_boe boe-a-2022-7191.html           # compare
    uv run python -m apps.api.devtools.ens_boe boe-a-2022-7191.html --write   # rewrite the records

Only the capture pinned in the pack's SOURCES.md is read; any other file is refused. The compare
prints every measure whose rebuilt hash differs from `requirements.yaml` or from
`source_records.json` and exits 1. A difference is reported, never fixed here: changing a hash is
a catalog content change (rule 10). SOURCES.md, "Source records", states the normalization.
"""

import argparse
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import yaml

PINNED_SHA256 = "6249bcb304bd17439c767cf2bd025df9a307c2781cf32c3154cdfe026a07f135"
SOURCE_URL = "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2022-7191"
PACK = Path(__file__).resolve().parents[3] / "catalog/frameworks/ens_rd311_2022"
RECORDS = PACK / "source_records.json"

# Where the pack's text knowingly differs from the record. The record keeps the hashed text, so
# its hash stays the one reviewed; the pack shows the corrected reading. One entry per fix.
# mp.s.2 (issue 249): the BOE marks up "<em>web </em>deberán"; trimming the inline text joined
# the two words, and the page reads "web deberán".
CORRECTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "mp.s.2": (("servicios webdeberán", "servicios web deberán"),),
}

_MEASURE = re.compile(r"^(\d+(?:\.\d+){1,2}) (.+) \[(org\.\d+|(?:op|mp)\.[a-z]+\.\d+)\]\.?$")
_GROUP = re.compile(r"^\d+\.\d+ .+ \[(?:op|mp)\.[a-z]+\]\.?$")
_CENTRED = "centro_cursiva"  # "4. Marco operacional [op]", "6. Valoración de la implantación..."
_INLINE = frozenset({"a", "b", "em", "i", "span", "strong", "sub", "sup", "u"})
_APPLICATION = "Aplicación de la medida"
_LEVEL_LINE = re.compile(r"^– (?:Nivel|Categoría) ")

type Record = dict[str, Any]
type Block = tuple[str, str, list[list[str]]]  # (class of a paragraph or "", text, table rows)


def _clean(text: str) -> str:
    """Runs of whitespace (no-break and typographic spaces included) become one space."""
    return " ".join(text.split())


class _Blocks(HTMLParser):
    """Paragraphs outside tables and whole tables, in document order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)  # entities are decoded before any other step
        self.blocks: list[Block] = []
        self._rows: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._class = ""
        self._text: list[list[str]] = []  # one buffer for the paragraph or cell, one per inline

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._rows = []
        elif tag == "tr" and self._rows is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._text = [[]]
        elif tag == "p" and self._rows is None:
            self._class = dict(attrs).get("class") or ""
            self._text = [[]]
        elif tag in _INLINE and self._text:
            self._text.append([])

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._rows is not None:
            self.blocks.append(("", "", self._rows))
            self._rows = None
        elif tag == "tr" and self._rows is not None and self._row is not None:
            self._rows.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._row is not None and self._text:
            self._row.append(_clean("".join(self._text[0])))
            self._text = []
        elif tag == "p" and self._rows is None and self._text:
            self.blocks.append((self._class, _clean("".join(self._text[0])), []))
            self._text = []
        elif tag in _INLINE and len(self._text) > 1:
            inner = "".join(self._text.pop())
            self._text[-1].append(inner.strip())  # trimmed before it joins the outer text

    def handle_data(self, data: str) -> None:
        if self._text:
            self._text[-1].append(data)


def records(page: str) -> list[Record]:
    """One record per Annex II measure, in the order of the page.

    A measure starts at its heading ("3.1 Política de seguridad [org.1].") and ends at the next
    measure heading, at a group heading ("4.1 Planificación [op.pl].") or at a centred heading.
    """
    parser = _Blocks()
    parser.feed(page)
    parser.close()
    found: list[Record] = []
    current: Record | None = None
    for css_class, text, rows in parser.blocks:
        heading = None if rows else _MEASURE.match(text)
        if heading:
            current = {
                "id": heading.group(3),
                "title_es": heading.group(2),
                "section": heading.group(1),
                "paragraphs": [],
                "tables": [],
            }
            found.append(current)
        elif current is None:
            continue
        elif rows:
            current["tables"].append(rows)
        elif css_class == _CENTRED or _GROUP.match(text):
            current = None
        elif text:  # a paragraph that holds only an image has no text and is left out
            current["paragraphs"].append(text)
    return found


def record_sha256(record: Record) -> str:
    """SHA-256 of the record as UTF-8 JSON: sorted keys, no ASCII escaping, default separators."""
    body = {key: record[key] for key in ("id", "title_es", "section", "paragraphs", "tables")}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def derive(record: Record) -> dict[str, Any]:
    """The pack fields that are copied from a record, as `requirements.yaml` holds them."""
    paragraphs: list[str] = record["paragraphs"]
    split = next(
        (i for i, text in enumerate(paragraphs) if text.startswith(_APPLICATION)), len(paragraphs)
    )
    if split == len(paragraphs):  # mp.info.6 lists its levels without the usual heading
        while split > 0 and _LEVEL_LINE.match(paragraphs[split - 1]):
            split -= 1
    official = "\n\n".join(paragraphs[:split])
    for wrong, right in CORRECTIONS.get(record["id"], ()):
        official = official.replace(wrong, right)
    summary = record["tables"][0]
    return {
        "title_es": record["title_es"],
        "section": record["section"],
        "official_text_es": official,
        "applicability_es": "\n".join(paragraphs[split:]),
        "selection_basis": f"{summary[1][0]} · {summary[0][1]}",
        "selection_rules": [
            {"level": level, "rule": rule}
            for level, rule in zip(summary[1][1:], summary[2][1:], strict=True)
        ],
    }


def read_pinned(path: Path) -> str:
    """The capture's text, or ValueError when the file is not the one SOURCES.md pins."""
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PINNED_SHA256:
        raise ValueError(f"{path.name} is not the pinned capture: SHA-256 {digest}")
    return raw.decode("utf-8")


def differences(rebuilt: list[Record]) -> list[str]:
    """Measures whose rebuilt record disagrees with the pack or with the committed records."""
    pack = yaml.safe_load((PACK / "requirements.yaml").read_text(encoding="utf-8"))["requirements"]
    stored = json.loads(RECORDS.read_text(encoding="utf-8"))["records"] if RECORDS.exists() else []
    hashes = {record["id"]: record_sha256(record) for record in rebuilt}
    kept = {record["id"]: record for record in stored}
    found = [
        f"{r['id']}: requirements.yaml has {r['attributes']['source_sha256']},"
        f" the capture gives {hashes.get(r['id'], 'no record')}"
        for r in pack
        if hashes.get(r["id"]) != r["attributes"]["source_sha256"]
    ]
    found += [
        f"{record['id']}: source_records.json differs from the capture"
        for record in rebuilt
        if kept.get(record["id"]) != record
    ]
    found += [
        f"{name}: in the capture but not in the pack"
        for name in hashes.keys() - {r["id"] for r in pack}
    ]
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="the BOE page saved to a local file")
    parser.add_argument("--write", action="store_true", help="rewrite source_records.json")
    args = parser.parse_args()
    try:
        rebuilt = records(read_pinned(args.path))
    except ValueError as refused:
        print(refused, file=sys.stderr)
        return 2
    if args.write:
        body = {"source": SOURCE_URL, "source_sha256": PINNED_SHA256, "records": rebuilt}
        RECORDS.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    found = differences(rebuilt)
    for line in found:
        print(line)
    print(f"{len(rebuilt)} measures rebuilt, {len(found)} differences")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
