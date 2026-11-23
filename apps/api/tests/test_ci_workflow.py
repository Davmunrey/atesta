"""CI supply-chain policy: the lock is enforced, CI tools are pinned and cooled down, and the
dependency audit reads the locked project dependencies (not the tool's own environment)."""

import json
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


def test_dependabot_keeps_the_seven_day_cooldown() -> None:
    """Version updates wait 7 days, like uv exclude-newer and pnpm minimumReleaseAge; every
    ecosystem the repo uses is covered."""
    config = yaml.safe_load((WORKFLOWS.parent / "dependabot.yml").read_text())
    updates = config["updates"]
    assert {u["package-ecosystem"] for u in updates} == {"uv", "npm", "github-actions", "opentofu"}
    assert all(u.get("cooldown", {}).get("default-days", 0) >= 7 for u in updates)


def test_node_types_follow_the_runtime_major() -> None:
    """@types/node stays on the Node runtime major; Dependabot may not bump it alone."""
    web = WORKFLOWS.parents[1] / "apps" / "web"
    runtime = (web / ".nvmrc").read_text().strip().split(".")[0]
    types = json.loads((web / "package.json").read_text())["devDependencies"]["@types/node"]
    assert types.lstrip("^~").split(".")[0] == runtime
    config = yaml.safe_load((WORKFLOWS.parent / "dependabot.yml").read_text())
    npm = next(u for u in config["updates"] if u["package-ecosystem"] == "npm")
    assert {"dependency-name": "@types/node", "update-types": ["version-update:semver-major"]} in (
        npm.get("ignore", [])
    )


# Workflow hardening (issue #106). Each check takes the workflow directory as an argument so a
# planted copy in tmp_path can prove it fails.

WRITE_SCOPES = re.compile(r":\s*write\b")
PINNED = re.compile(r"uses:\s*[\w.-]+/[\w./-]+@[0-9a-f]{40}\s+#\s*v\d")


def _workflow_files(root: Path = WORKFLOWS) -> list[Path]:
    return sorted(root.glob("*.yml"))


def unpinned_actions(root: Path = WORKFLOWS) -> list[str]:
    bad = []
    for path in _workflow_files(root):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            stripped = line.strip().removeprefix("- ")
            if not stripped.startswith("uses:") or stripped.startswith("uses: ./"):
                continue
            if not PINNED.match(stripped):
                bad.append(f"{path.name}:{number}: {stripped}")
    return bad


def top_level_write(root: Path = WORKFLOWS) -> list[str]:
    bad = []
    for path in _workflow_files(root):
        permissions = yaml.safe_load(path.read_text()).get("permissions")
        if not isinstance(permissions, dict):
            bad.append(f"{path.name}: no top-level permissions map")
        elif "write" in permissions.values():
            bad.append(f"{path.name}: top-level write")
    return bad


def jobs_without_timeout(root: Path = WORKFLOWS) -> list[str]:
    bad = []
    for path in _workflow_files(root):
        for name, job in yaml.safe_load(path.read_text())["jobs"].items():
            if "uses" not in job and "timeout-minutes" not in job:
                bad.append(f"{path.name}: {name}")
    return bad


def test_every_action_is_pinned_to_a_commit_with_its_version() -> None:
    assert unpinned_actions() == []


def test_no_workflow_grants_write_at_the_top_level() -> None:
    assert top_level_write() == []


def test_every_job_has_a_timeout() -> None:
    assert jobs_without_timeout() == []


def test_ci_cancels_only_superseded_pull_request_runs() -> None:
    concurrency = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())["concurrency"]
    assert "pull_request.number" in concurrency["group"]
    assert concurrency["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"


PLANTED = """
name: planted
on: [push]
permissions:
  contents: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@0123456789abcdef0123456789abcdef01234567
"""


def test_the_guards_catch_a_planted_workflow(tmp_path: Path) -> None:
    (tmp_path / "planted.yml").write_text(PLANTED)
    assert len(unpinned_actions(tmp_path)) == 2  # a tag, and a SHA with no version comment
    assert top_level_write(tmp_path) == ["planted.yml: top-level write"]
    assert jobs_without_timeout(tmp_path) == ["planted.yml: build"]


# The main-branch ruleset (issue #112) requires exactly the CI jobs, so a job added to ci.yml
# without being required, or a required name no job produces (which blocks every merge), fails.

RULESET = WORKFLOWS.parent / "rulesets" / "main-branch.json"


def ruleset_gaps(ruleset: dict[str, Any], workflow: dict[str, Any]) -> tuple[set[str], set[str]]:
    rule = next(r for r in ruleset["rules"] if r["type"] == "required_status_checks")
    required = {check["context"] for check in rule["parameters"]["required_status_checks"]}
    jobs = set(workflow["jobs"])
    return jobs - required, required - jobs


def test_the_ruleset_requires_every_ci_job_and_nothing_else() -> None:
    ruleset = json.loads(RULESET.read_text())
    workflow = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())
    assert ruleset_gaps(ruleset, workflow) == (set(), set())


def test_the_ruleset_protects_main() -> None:
    ruleset = json.loads(RULESET.read_text())
    types = {rule["type"] for rule in ruleset["rules"]}
    assert {"deletion", "non_fast_forward", "pull_request", "required_status_checks"} <= types
    assert ruleset["enforcement"] == "active"
    assert ruleset["bypass_actors"] == []
    pull_request = next(r for r in ruleset["rules"] if r["type"] == "pull_request")
    assert pull_request["parameters"]["allowed_merge_methods"] == ["squash"]


def test_a_job_missing_from_the_ruleset_is_caught() -> None:
    ruleset = json.loads(RULESET.read_text())
    workflow = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())
    workflow["jobs"]["planted"] = {"runs-on": "ubuntu-latest"}
    assert ruleset_gaps(ruleset, workflow) == ({"planted"}, set())


def test_ci_also_runs_weekly_and_on_demand() -> None:
    # yaml.safe_load reads the `on:` key as True (YAML 1.1).
    triggers = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())[True]
    assert {"push", "pull_request", "schedule", "workflow_dispatch"} <= set(triggers)
    assert triggers["schedule"][0]["cron"]


def test_pull_request_only_work_stays_off_other_runs() -> None:
    jobs = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())["jobs"]
    assert jobs["changes"]["if"] == "github.event_name == 'pull_request'"
    guide = yaml.safe_load((WORKFLOWS / "pr-guide.yml").read_text())["jobs"]["guide"]
    assert "github.event.workflow_run.event == 'pull_request'" in guide["if"]


def test_the_secret_scan_is_pinned_verified_and_redacted() -> None:
    job = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())["jobs"]["secrets"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", job["env"]["GITLEAKS_VERSION"])
    assert re.fullmatch(r"[0-9a-f]{64}", job["env"]["GITLEAKS_SHA256"])
    run = "\n".join(step.get("run", "") for step in job["steps"])
    assert "sha256sum --check --strict" in run
    assert "--redact" in run
    assert job["steps"][0]["with"]["fetch-depth"] == 0


def test_procrastinate_bumps_are_guarded_by_the_queue_migration_test() -> None:
    # The owner lifted the Dependabot ignore on 2026-11-23. A bump that ships queue SQL still needs
    # a vendored, reviewed migration (#122, #123): tests/db/test_queue_migrations.py fails it.
    config = yaml.safe_load((WORKFLOWS.parent / "dependabot.yml").read_text())
    uv = next(u for u in config["updates"] if u["package-ecosystem"] == "uv")
    assert {"dependency-name": "procrastinate"} not in uv.get("ignore", [])
    guard = WORKFLOWS.parents[1] / "apps" / "api" / "tests" / "db" / "test_queue_migrations.py"
    assert "def test_the_installed_procrastinate_ships_no_queue_migration" in guard.read_text()


def test_dependabot_bumps_opentofu_providers_in_one_pull_request() -> None:
    # Per-directory pull requests left modules and the lock file out of step (#125-#127).
    config = yaml.safe_load((WORKFLOWS.parent / "dependabot.yml").read_text())
    tofu = next(u for u in config["updates"] if u["package-ecosystem"] == "opentofu")
    assert tofu["groups"]["opentofu-providers"]["patterns"] == ["*"]
