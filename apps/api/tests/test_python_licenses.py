"""Python licence gate (issue #119): each refusal is proven with planted metadata."""

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/api, as test_changes does
licences: Any = importlib.import_module("devtools.python_licenses")


@pytest.mark.parametrize(
    "text",
    [
        "MIT",
        "Apache-2.0",
        "BSD-3-Clause",
        "License :: OSI Approved :: MIT License",
        "MPL-2.0",
        "PSF-2.0",
    ],
)
def test_permissive_licences_pass(text: str) -> None:
    assert licences.classify("somelib", text) is None


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("GPL-3.0-only", "GPL"),
        ("GPL-2.0-or-later", "GPL"),
        ("License :: OSI Approved :: GNU General Public License v3 (GPLv3)", "GPL"),
        ("AGPL-3.0-only", "AGPL"),
        ("License :: OSI Approved :: GNU Affero General Public License v3", "AGPL"),
    ],
)
def test_gpl_and_agpl_fail(text: str, kind: str) -> None:
    problem = licences.classify("badlib", text)
    assert problem is not None and f"badlib: {kind} " in problem


def test_lgpl_passes_only_for_the_listed_libraries() -> None:
    assert licences.classify("psycopg", "LGPL-3.0-only") is None
    lesser = "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)"
    assert licences.classify("psycopg-pool", lesser) is None
    assert "LGPL not listed" in licences.classify("otherlib", "LGPL-3.0-only")


def test_dual_licences_with_gpl_fail() -> None:
    assert licences.classify("dual", "MIT OR GPL-3.0-only") is not None


def test_an_undeclared_licence_fails_unless_known(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "no licence declared" in licences.classify("mystery", "")
    monkeypatch.setitem(licences.KNOWN, "mystery", "MIT, read from its LICENSE file")
    assert licences.classify("mystery", "") is None


def test_the_workspace_itself_is_skipped() -> None:
    assert licences.classify("atesta-api", "") is None


def test_the_installed_environment_passes() -> None:
    installed = [
        (d.metadata["Name"].lower(), licences.licence_text(d.metadata))
        for d in importlib.metadata.distributions()
    ]
    assert licences.problems(installed) == []
