"""lint-imports breaks on a deliberate tenancy import outside identity (tenant-data-layer spec).

The source tree is copied to tmp_path and linted there; PYTHONPATH points at the copy, otherwise
grimp would analyse the installed package and the test would pass for the wrong reason.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TENANCY = "from atesta_api.platform.tenancy import set_tenant_context  # noqa: F401\n"
CASES = {
    "existing module": ("modules/compliance/scoring.py", TENANCY, "tenant context"),
    "new module": ("modules/reports/__init__.py", TENANCY, "tenant context"),
    "platform module": ("platform/audit.py", TENANCY, "tenant context"),
    "new top-level module": ("jobs.py", TENANCY, "tenant context"),
    "new module reaching identity internals": (
        "modules/reports/__init__.py",
        "from atesta_api.modules.identity import deps  # noqa: F401\n",
        "talk only through their public api.py",
    ),
}


def lint(tmp_path: Path, edit: tuple[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    shutil.copy(REPO / "pyproject.toml", tmp_path / "pyproject.toml")
    src = tmp_path / "src"
    ignore = shutil.ignore_patterns("__pycache__")
    shutil.copytree(REPO / "apps" / "api" / "src", src, ignore=ignore)
    if edit:
        target = src / "atesta_api" / edit[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((target.read_text() if target.exists() else "") + edit[1])
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
def test_deliberate_import_breaks_a_contract(tmp_path: Path, case: str) -> None:
    path, line, contract = CASES[case]
    result = lint(tmp_path, (path, line))
    assert result.returncode != 0
    assert contract in result.stdout
