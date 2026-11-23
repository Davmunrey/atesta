"""Deploy workflow (hosted-environment spec, issue #219): manual, OIDC only, migrations first."""

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
TEXT = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()
WORKFLOW: dict[str, Any] = yaml.safe_load(TEXT)
JOB = WORKFLOW["jobs"]["deploy"]
STEPS = [step.get("name", "") for step in JOB["steps"]]


def test_deploys_only_by_hand_from_main_into_a_protected_environment() -> None:
    assert set(WORKFLOW[True]) == {"workflow_dispatch"}  # yaml reads `on:` as True
    choice = WORKFLOW[True]["workflow_dispatch"]["inputs"]["environment"]
    assert choice["options"] == ["dev", "prod"]
    assert JOB["environment"] == "${{ inputs.environment }}"
    assert "refs/heads/main" in next(s["run"] for s in JOB["steps"] if s.get("name") == "Main only")
    assert WORKFLOW["concurrency"]["cancel-in-progress"] is False


def test_uses_short_lived_oidc_credentials_and_least_permissions() -> None:
    assert WORKFLOW["permissions"] == {}
    assert JOB["permissions"] == {"contents": "read", "id-token": "write"}
    assert "AWS_ACCESS_KEY_ID" not in TEXT and "aws-secret-access-key" not in TEXT
    login = next(s for s in JOB["steps"] if "configure-aws-credentials" in s.get("uses", ""))
    assert login["with"]["role-to-assume"] == "${{ vars.AWS_APPLY_ROLE_ARN }}"


def test_migrations_run_and_succeed_before_the_services_change() -> None:
    order = ["Build and push images", "Build the web app", "Run migrations", "Apply", "Upload web"]
    assert [STEPS.index(name) for name in order] == sorted(STEPS.index(name) for name in order)
    migrate = next(s["run"] for s in JOB["steps"] if s.get("name") == "Run migrations")
    # Quoted, so the shell never globs the brackets (actionlint SC2102).
    assert "'-target=module.platform.module.ecs[0].aws_ecs_task_definition.this[\"migrate\"]'" in (
        migrate
    )
    assert "exitCode" in migrate  # a failed migration stops the deploy


def test_ends_with_a_smoke_check_of_headers_and_the_api() -> None:
    smoke = next(s["run"] for s in JOB["steps"] if s.get("name") == "Smoke")
    assert "content-security-policy" in smoke and "strict-transport-security" in smoke
    assert "/api/v1/me" in smoke and "401" in smoke
