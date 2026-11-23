"""The Official Journal reader keeps wording verbatim; only whitespace is normalized."""

import importlib
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/api, as test_changes does
articles: Any = importlib.import_module("devtools.eu_act").articles

DOC = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body>
<p class="oj-ti-section-1">CAPÍTULO IV</p>
<p class="oj-ti-art">Artículo 21</p>
<p class="oj-sti-art">Medidas sintéticas</p>
<p class="oj-normal">1.   Primer   apartado, tal cual;</p>
<table><tr><td><p class="oj-normal">a)</p></td>
<td><p class="oj-normal">la letra a;</p></td></tr></table>
<p class="oj-ti-art">Artículo 22</p>
<p class="oj-sti-art">Otro</p>
<p class="oj-normal">Texto.</p>
<p class="oj-ti-grseq-1">ANEXO I</p>
<p class="oj-normal">Esto no pertenece a ningún artículo.</p>
</body></html>"""


def test_articles_keep_wording_points_and_order() -> None:
    found = articles(DOC.encode())
    assert [(a.number, a.title) for a in found] == [("21", "Medidas sintéticas"), ("22", "Otro")]
    assert found[0].heading == "Artículo 21"
    assert found[0].paragraphs == ["1. Primer apartado, tal cual;", "a) la letra a;"]
    assert found[1].paragraphs == ["Texto."]  # the annex text after the heading is not kept
