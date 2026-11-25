"""Import boundaries of the operator service (ADR-017, "Code boundaries"; operator-portal spec,
"Import-linter contracts"). Both source trees are copied to tmp_path and linted there, with
PYTHONPATH on the copies, so the test cannot pass by linting the installed packages."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
CASES = {
    "a module's internals": (
        "atesta_operator/me.py",
        "from atesta_api.modules.identity import deps  # noqa: F401\n",
        "calls modules only through their api.py",
    ),
    "tenancy": (
        "atesta_operator/me.py",
        "from atesta_api.platform import tenancy  # noqa: F401\n",
        "calls modules only through their api.py",
    ),
    "the queue": (
        "atesta_operator/me.py",
        "from atesta_api.platform import queue  # noqa: F401\n",
        "calls modules only through their api.py",
    ),
    "the customer API's entry point": (
        "atesta_operator/me.py",
        "from atesta_api import main  # noqa: F401\n",
        "calls modules only through their api.py",
    ),
    "the customer API importing the operator service": (
        "atesta_api/modules/identity/routes.py",
        "import atesta_operator.policy  # noqa: F401\n",
        "never import the operator service",
    ),
    "the worker importing the operator service": (
        "atesta_worker/jobs.py",
        "import atesta_operator.policy  # noqa: F401\n",
        "never import the operator service",
    ),
}


def lint(tmp_path: Path, edit: tuple[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    shutil.copy(REPO / "pyproject.toml", tmp_path / "pyproject.toml")
    src = tmp_path / "src"
    ignore = shutil.ignore_patterns("__pycache__")
    for app in ("api", "operator", "worker"):
        shutil.copytree(REPO / "apps" / app / "src", src, ignore=ignore, dirs_exist_ok=True)
    if edit:
        target = src / edit[0]
        target.write_text(target.read_text() + edit[1])
    return subprocess.run(  # noqa: S603  fixed argv, no shell
        [str(Path(sys.executable).with_name("lint-imports")), "--no-cache"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(src)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_unmodified_copy_is_kept(tmp_path: Path) -> None:
    result = lint(tmp_path)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("case", sorted(CASES))
def test_a_deliberate_import_breaks_a_contract(tmp_path: Path, case: str) -> None:
    path, line, contract = CASES[case]
    result = lint(tmp_path, (path, line))
    assert result.returncode != 0
    assert contract in result.stdout
