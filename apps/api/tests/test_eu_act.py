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


annex_points: Any = importlib.import_module("devtools.eu_act").annex_points

ANNEX = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<body>
<p class="oj-ti-art">Artículo 2</p>
<p class="oj-normal">No es del anexo.</p>
<div id="anx_1">
<div class="eli-container">
<p class="oj-doc-ti">ANEXO</p>
<p class="oj-ti-grseq-1">1.   Política sintética</p>
<p class="oj-ti-grseq-1">1.1.   Primera sección</p>
<table>
<col/>
<col/>
<col/>
<tbody>
<tr>
<td/>
<td>
<p class="oj-normal">1.1.1.</p>
</td>
<td>
<span>La política   deberá:</span>
<table>
<col/>
<col/>
<tbody>
<tr>
<td>
<p class="oj-normal">a)</p>
</td>
<td>
<p class="oj-normal">la letra a, con:</p>
<table>
<col/>
<col/>
<tbody>
<tr>
<td>
<p class="oj-normal">i)</p>
</td>
<td>
<p class="oj-normal">un inciso;</p>
</td>
</tr>
</tbody>
</table>
</td>
</tr>
</tbody>
</table>
<table>
<col/>
<col/>
<tbody>
<tr>
<td>
<p class="oj-normal">b)</p>
</td>
<td>
<p class="oj-normal">la letra b.</p>
</td>
</tr>
</tbody>
</table>
Texto final suelto.</td>
</tr>
</tbody>
</table>
<p class="oj-ti-grseq-1">1.2.   Sección sin puntos numerados</p>
<p class="oj-normal">Las entidades llevarán un registro que incluya:</p>
<table>
<col/>
<col/>
<tbody>
<tr>
<td>
<p class="oj-normal">a)</p>
</td>
<td>
<p class="oj-normal">contactos.</p>
</td>
</tr>
</tbody>
</table>
<p class="oj-ti-grseq-1">2.   Otra política</p>
<p class="oj-ti-grseq-1">2.1.   Sección</p>
<table>
<col/>
<col/>
<col/>
<tbody>
<tr>
<td/>
<td>
<p class="oj-normal">2.1.1.</p>
</td>
<td>
<p class="oj-normal">Un punto.</p>
</td>
</tr>
</tbody>
</table>
</div>
</div>
</body>
</html>"""


def test_annex_points_keep_numbers_letters_and_loose_text() -> None:
    headings, points = annex_points(ANNEX.encode())
    assert headings == {
        "1": "1. Política sintética",
        "1.1": "1.1. Primera sección",
        "1.2": "1.2. Sección sin puntos numerados",
        "2": "2. Otra política",
        "2.1": "2.1. Sección",
    }
    assert [(p.number, p.section) for p in points] == [
        ("1.1.1", "1.1"),
        ("1.2", "1.2"),
        ("2.1.1", "2.1"),
    ]
    assert points[0].paragraphs == [
        "La política deberá:",
        "a) la letra a, con:\n  i) un inciso;",
        "b) la letra b.",
        "Texto final suelto.",
    ]
    assert points[1].paragraphs == [
        "Las entidades llevarán un registro que incluya:",
        "a) contactos.",
    ]
    assert points[2].paragraphs == ["Un punto."]
