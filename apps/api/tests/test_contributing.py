"""CONTRIBUTING.md lists the commands CI runs, and only those (issue #108). A command copied
into the docs that CI no longer runs, or that never ran in CI, fails here."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
SECTION = "## Check before you push"


def documented_commands(markdown: str) -> list[str]:
    section = markdown.split(SECTION, 1)[1].split("\n## ", 1)[0]
    commands = []
    for block in re.findall(r"```bash\n(.*?)```", section, flags=re.DOTALL):
        for line in block.splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "export ")):
                commands.append(line)
    return commands


def ci_commands(workflow: Path) -> set[str]:
    commands = set()
    for job in yaml.safe_load(workflow.read_text())["jobs"].values():
        for step in job.get("steps", []):
            commands.update(line.strip() for line in step.get("run", "").splitlines())
    return commands


def missing_from_ci(markdown: str, workflow: Path) -> list[str]:
    ci = ci_commands(workflow)
    return [command for command in documented_commands(markdown) if command not in ci]


def test_every_documented_check_is_a_ci_command() -> None:
    markdown = (ROOT / "CONTRIBUTING.md").read_text()
    assert len(documented_commands(markdown)) >= 15
    assert missing_from_ci(markdown, ROOT / ".github" / "workflows" / "ci.yml") == []


def test_a_command_ci_does_not_run_is_caught() -> None:
    markdown = (ROOT / "CONTRIBUTING.md").read_text()
    planted = markdown.replace("uv run mypy\n", "uv run mypy --no-strict\n", 1)
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    assert missing_from_ci(planted, workflow) == ["uv run mypy --no-strict"]
