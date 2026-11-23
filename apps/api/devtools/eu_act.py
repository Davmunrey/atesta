"""Read articles from an Official Journal act captured from the EU Publications Office.

Capture (both languages, same CELEX, outside CI; EUR-Lex HTML answers bots with a challenge):

    curl -sSL -H "Accept: application/xhtml+xml" -H "Accept-Language: spa" \\
      -o act-es.xhtml http://publications.europa.eu/resource/celex/32022L2555

Then `uv run python -m apps.api.devtools.eu_act act-es.xhtml 20 21 23` prints the articles as
JSON: number, heading, title and paragraphs, with lettered points kept as "a) text". With
`--annex`, it prints the first annex instead: its numbered headings, and each numbered point
("1.1.1") with its paragraphs; a subsection without numbered points becomes one point. The only
normalization is whitespace (no-break spaces and runs of spaces become one space); wording,
spelling and punctuation are the Journal's. Pack SOURCES.md files record the capture hashes.
"""

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

_XHTML = "{http://www.w3.org/1999/xhtml}"
_SPACE = re.compile(r"\s+")


@dataclass
class Article:
    number: str
    heading: str
    title: str
    paragraphs: list[str] = field(default_factory=list)


def _text(element: ET.Element) -> str:
    return _SPACE.sub(" ", "".join(element.itertext()).replace("\xa0", " ")).strip()


def _classes(element: ET.Element) -> set[str]:
    return set((element.get("class") or "").split())


def articles(document: bytes) -> list[Article]:
    """Every article in document order. A table row of a lettered point becomes one paragraph."""
    # A local devtool reading an official capture: expat caps entity expansion and
    # ElementTree never fetches external entities.
    root = ET.fromstring(document)  # noqa: S314 - official capture, no external entities
    found: list[Article] = []
    current: Article | None = None
    for element in root.iter():
        tag = element.tag.removeprefix(_XHTML)
        classes = _classes(element)
        if tag == "p" and "oj-ti-art" in classes:
            text = _text(element)
            current = Article(number=text.split(" ")[-1], heading=text, title="")
            found.append(current)
        elif current is None:
            continue
        elif tag == "p" and "oj-sti-art" in classes:
            current.title = _text(element)
        elif tag == "tr":
            cells = [_text(c) for c in element if c.tag.removeprefix(_XHTML) == "td"]
            if any(cells):
                current.paragraphs.append(" ".join(c for c in cells if c))
        elif tag == "p" and "oj-normal" in classes and not _inside_table(element, root):
            current.paragraphs.append(_text(element))
        elif tag == "p" and ({"oj-ti-section-1", "oj-ti-grseq-1"} & classes):
            current = None  # a chapter or annex heading ends the article
    return found


@dataclass
class AnnexPoint:
    number: str
    section: str
    paragraphs: list[str] = field(default_factory=list)


_POINT = re.compile(r"^(\d+(?:\.\d+)+)\.$")
_HEADING = re.compile(r"^(\d+(?:\.\d+)?)\.\s")
_LABEL = re.compile(r"^(?:\(?[a-z]{1,4}\)|\(?[ivx]+\)|—|–)$")


def _cells(row: ET.Element) -> list[ET.Element]:
    return [c for c in row if c.tag.removeprefix(_XHTML) == "td"]


def _rows(table: ET.Element) -> list[ET.Element]:
    """Rows of this table only, not of tables nested in its cells."""
    rows = [r for r in table if r.tag.removeprefix(_XHTML) == "tr"]
    bodies = [b for b in table if b.tag.removeprefix(_XHTML) == "tbody"]
    return rows + [r for b in bodies for r in b if r.tag.removeprefix(_XHTML) == "tr"]


def _lettered(table: ET.Element) -> list[str]:
    """A lettered (or dashed) list laid out as a table: "a) text", nested lists indented."""
    out: list[str] = []
    for row in _rows(table):
        cells = _cells(row)
        if len(cells) >= 2 and _LABEL.match(_text(cells[-2])):
            body = "\n".join(_flow(cells[-1]))
            out.append(f"{_text(cells[-2])} {body}".replace("\n", "\n  "))
        elif _text(row):
            out.append(_text(row))
    return out


def _flow(elements: ET.Element | list[ET.Element], lead: str = "") -> list[str]:
    """Paragraphs in document order: loose text (including .text and .tail strings) and
    paragraphs, with each lettered table expanded by _lettered."""
    out: list[str] = []
    buffer = [lead]

    def flush() -> None:
        text = _SPACE.sub(" ", "".join(buffer).replace("\xa0", " ")).strip()
        if text:
            out.append(text)
        buffer.clear()

    children = list(elements)
    if isinstance(elements, ET.Element):
        buffer.append(elements.text or "")
    for child in children:
        tag = child.tag.removeprefix(_XHTML)
        if tag == "table":
            flush()
            out.extend(_lettered(child))
        elif tag == "p":
            flush()
            buffer.append("".join(child.itertext()))
            flush()
        else:
            buffer.append("".join(child.itertext()))
        buffer.append(child.tail or "")
    flush()
    return out


def annex_points(document: bytes) -> tuple[dict[str, str], list[AnnexPoint]]:
    """The first annex: its numbered headings ("1", "1.1") and numbered points in order."""
    root = ET.fromstring(document)  # noqa: S314 - official capture, no external entities
    annex = next(e for e in root.iter() if e.get("id") == "anx_1")
    headings: dict[str, str] = {}
    points: list[AnnexPoint] = []
    loose: list[ET.Element] = []
    section = ""

    def close_loose() -> None:
        if loose and section and "." in section:
            points.append(AnnexPoint(section, section, _flow(loose)))
        loose.clear()

    containers = [
        e
        for e in annex.iter()
        if any(c.tag.removeprefix(_XHTML) == "p" and "oj-ti-grseq-1" in _classes(c) for c in e)
    ]
    for container in containers:  # the level that holds the headings; never inside a point
        for child in container:
            tag = child.tag.removeprefix(_XHTML)
            if tag == "p" and "oj-ti-grseq-1" in _classes(child):
                close_loose()
                match = _HEADING.match(_text(child))
                if match:
                    section = match.group(1)
                    headings[section] = _text(child)
            elif tag == "table" and _rows(child):
                cells = _cells(_rows(child)[0])
                number = _POINT.match(_text(cells[-2])) if len(cells) >= 2 else None
                if number:
                    close_loose()
                    points.append(AnnexPoint(number.group(1), section, _flow(cells[-1])))
                elif section:
                    loose.append(child)
            elif tag == "p" and "oj-normal" in _classes(child) and section:
                loose.append(child)
    close_loose()
    return headings, points


def _inside_table(element: ET.Element, root: ET.Element) -> bool:
    parents = {child: parent for parent in root.iter() for child in parent}
    node: ET.Element | None = parents.get(element)
    while node is not None:
        if node.tag.removeprefix(_XHTML) == "table":
            return True
        node = parents.get(node)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("numbers", nargs="*", help="article numbers; all when omitted")
    parser.add_argument("--annex", action="store_true", help="read the first annex instead")
    args = parser.parse_args()
    raw = args.path.read_bytes()
    if args.annex:
        headings, points = annex_points(raw)
        annex = {"headings": headings, "points": [asdict(p) for p in points]}
        json.dump(
            {"sha256": hashlib.sha256(raw).hexdigest(), "annex": annex},
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        return
    wanted = set(args.numbers)
    out = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "articles": [asdict(a) for a in articles(raw) if not wanted or a.number in wanted],
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
