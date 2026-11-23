"""Read articles from an Official Journal act captured from the EU Publications Office.

Capture (both languages, same CELEX, outside CI; EUR-Lex HTML answers bots with a challenge):

    curl -sSL -H "Accept: application/xhtml+xml" -H "Accept-Language: spa" \\
      -o act-es.xhtml http://publications.europa.eu/resource/celex/32022L2555

Then `uv run python -m apps.api.devtools.eu_act act-es.xhtml 20 21 23` prints the articles as
JSON: number, heading, title and paragraphs, with lettered points kept as "a) text". The only
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
    args = parser.parse_args()
    raw = args.path.read_bytes()
    wanted = set(args.numbers)
    out = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "articles": [asdict(a) for a in articles(raw) if not wanted or a.number in wanted],
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
