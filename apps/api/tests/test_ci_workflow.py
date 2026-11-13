"""CI supply-chain policy: the lock is enforced, CI tools are pinned and cooled down, and the
dependency audit reads the locked project dependencies (not the tool's own environment)."""

import re
from pathlib import Path
from typing import Any

import yaml

WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"


def _steps() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for job in yaml.safe_load(path.read_text())["jobs"].values():
            steps += job.get("steps", [])
    return steps


def _commands() -> list[str]:
    lines = (line.strip() for step in _steps() for line in step.get("run", "").splitlines())
    return [line for line in lines if line]


def test_uv_sync_enforces_the_lock() -> None:
    syncs = [c for c in _commands() if c.startswith("uv sync")]
    assert syncs
    assert [c for c in syncs if "--locked" not in c and "--frozen" not in c] == []


def test_uvx_tools_are_pinned_and_cooled_down() -> None:
    tools = [c for c in _commands() if c.startswith("uvx ")]
    assert tools
    unpinned = [c for c in tools if "--exclude-newer" not in c or not re.search(r"==\d", c)]
    assert unpinned == []


def test_dependency_audit_reads_the_exported_lock() -> None:
    audits = [c for c in _commands() if "pip-audit" in c]
    assert audits
    assert all(" -r " in c and "--require-hashes" in c for c in audits)
    assert any(c.startswith("uv export") and "--locked" in c for c in _commands())


def test_checkout_does_not_persist_the_token() -> None:
    checkouts = [s for s in _steps() if s.get("uses", "").startswith("actions/checkout@")]
    assert checkouts
    assert all(s.get("with", {}).get("persist-credentials") is False for s in checkouts)


def test_setup_uv_pins_the_uv_version() -> None:
    setups = [s for s in _steps() if s.get("uses", "").startswith("astral-sh/setup-uv@")]
    assert setups
    assert all(re.fullmatch(r"\d+\.\d+\.\d+", s.get("with", {}).get("version", "")) for s in setups)
