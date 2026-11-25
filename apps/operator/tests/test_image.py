"""Images (ADR-017, "Images"; operator-portal spec, acceptance criterion "Separate application").

The customer API and worker images hold no operator code, and the operator image holds no worker.
One Dockerfile builds all three, so the check follows each target's stages: the stage it starts
from and every stage it copies from. CI's images job also checks the built images.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = (ROOT / "apps" / "Dockerfile").read_text()
IGNORE = (ROOT / "apps" / "Dockerfile.dockerignore").read_text()
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text()


def _stages() -> dict[str, tuple[str, str]]:
    """Stage name -> (parent image or stage, body)."""
    stages: dict[str, tuple[str, str]] = {}
    for chunk in re.split(r"^(?=FROM )", DOCKERFILE, flags=re.M)[1:]:
        head, _, body = chunk.partition("\n")
        match = re.fullmatch(r"FROM (\S+) AS (\S+)", head.strip())
        assert match, head
        stages[match[2]] = (match[1], body)
    return stages


def _closure(target: str) -> str:
    """Every line of the target's own stages, following FROM and COPY --from."""
    stages, seen, todo = _stages(), set[str](), [target]
    while todo:
        name = todo.pop()
        if name in seen or name not in stages:
            continue
        seen.add(name)
        parent, body = stages[name]
        todo += [parent, *re.findall(r"COPY --from=(\S+)", body)]
    return "\n".join(stages[name][1] for name in seen)


def test_the_api_and_worker_images_never_copy_or_build_the_operator_service() -> None:
    for target in ("api", "worker"):
        lines = _closure(target)
        assert "apps/operator" not in lines, target
        assert "atesta-operator" not in lines and "atesta_operator" not in lines, target
        # Third-party packages come from the worker's closure, which excludes the operator.
        assert re.search(r"uv export .*--package atesta-worker", lines), target


def test_the_operator_image_builds_its_own_closure_without_the_worker() -> None:
    lines = _closure("operator")
    assert re.search(r"uv export .*--package atesta-operator", lines)
    assert "/src/apps/operator" in lines and "/src/apps/api" in lines  # it calls modules' api.py
    assert "apps/worker" not in lines and "atesta-worker" not in lines
    assert "migrations" not in lines and "scanner/expected" not in lines
    assert 'CMD ["uvicorn", "atesta_operator.main:app"' in lines
    assert "USER 10001" in lines
    assert "!apps/operator/src/**" in IGNORE


def test_ci_checks_the_built_images_in_both_directions() -> None:
    no_operator = 'find_spec("atesta_operator") is not None'
    assert any("atesta-api:ci python" in line and no_operator in line for line in CI.splitlines())
    no_worker = 'find_spec("atesta_worker") is not None'
    assert any(
        "atesta-operator:ci python" in line and no_worker in line for line in CI.splitlines()
    )
    assert "--target operator -t atesta-operator:ci" in CI
