"""The customer API image holds no operator code (ADR-017, "Images"; operator-portal spec,
acceptance criterion "Separate application"). The operator's own image comes with the
infrastructure step (spec, "Build order" 6); CI's images job also checks the built API image."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = (ROOT / "apps" / "Dockerfile").read_text()
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text()


def test_the_api_image_never_copies_or_builds_the_operator_service() -> None:
    assert "apps/operator" not in DOCKERFILE
    assert "atesta-operator" not in DOCKERFILE and "atesta_operator" not in DOCKERFILE
    # Third-party packages are exported for the worker's closure, which excludes the operator.
    assert re.search(r"uv export .*--package atesta-worker", DOCKERFILE)


def test_ci_checks_the_built_api_image_has_no_operator_module() -> None:
    probe = 'find_spec("atesta_operator") is not None'
    assert any("atesta-api:ci python" in line and probe in line for line in CI.splitlines())
