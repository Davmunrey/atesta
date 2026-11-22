"""Changelog fragments (issue #110): each guard in apps/api/devtools/changes.py is proven by
planting the fault it catches."""

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/api, as test_fake_cognito does
changes: Any = importlib.import_module("devtools.changes")
FRAGMENT, check, fragment_problem = changes.FRAGMENT, changes.check, changes.fragment_problem

ROOT = Path(__file__).resolve().parents[3]
GOOD = "**Connections are verified read-only before every scan.** (#91) Extra grants stop it."
BODY = "Fixes #91\n\n## What this changes\n"


def test_a_good_fragment_passes() -> None:
    assert check({"91.added.md": GOOD}, ["changes/91.added.md"], BODY, "Davmunrey") == []


def test_no_fragment_fails() -> None:
    assert check({}, ["apps/api/x.py"], BODY, "Davmunrey") == [
        "add a fragment: changes/<issue>.<kind>.md (changes/README.md)"
    ]


@pytest.mark.parametrize("name", ["91.feature.md", "fix-91.added.md", "91.added.txt", "91.md"])
def test_a_misnamed_fragment_fails(name: str) -> None:
    assert fragment_problem(name, GOOD) is not None


@pytest.mark.parametrize(
    "body",
    [
        "Connections are verified. (#91)",  # not bold
        "**Connections are verified.** (#92)",  # wrong issue
        "- **Connections are verified.** (#91)",  # list marker
        "## Added\n**Connections are verified.** (#91)",  # heading
    ],
)
def test_a_malformed_fragment_fails(body: str) -> None:
    assert fragment_problem("91.added.md", body) is not None


def test_a_fragment_for_an_issue_the_body_does_not_fix_fails() -> None:
    problems = check({"91.added.md": GOOD}, [], "Fixes #90", "Davmunrey")
    assert problems == ["91.added.md: issue #91 is not in the body's Fixes lines"]


def test_a_second_entry_for_the_same_issue_is_allowed() -> None:
    second = "**A fix for the same issue.** (#91)"
    assert check({"91.added.md": GOOD, "91-2.fixed.md": second}, [], BODY, "Davmunrey") == []


def test_editing_the_changelog_outside_a_release_fails() -> None:
    problems = check({"91.added.md": GOOD}, ["CHANGELOG.md"], BODY, "Davmunrey")
    assert problems == ["CHANGELOG.md is edited only by a release; add a file in changes/"]


def test_a_release_may_edit_the_changelog_and_add_no_fragment() -> None:
    body = "Fixes #120\nRelease: v2026.12.0\n"
    assert check({}, ["CHANGELOG.md", "changes/91.added.md"], body, "Davmunrey") == []


def test_dependabot_is_exempt() -> None:
    assert check({}, ["uv.lock"], "Bumps x", "dependabot[bot]") == []


def test_every_committed_fragment_is_valid() -> None:
    for path in sorted((ROOT / "changes").glob("*.md")):
        if path.name != "README.md":
            assert FRAGMENT.match(path.name), path.name
            assert fragment_problem(path.name, path.read_text()) is None, path.name


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)  # noqa: S603, S607


def test_the_cli_reads_a_real_branch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(
        tmp_path,
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "base",
    )
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    (tmp_path / "changes").mkdir()
    (tmp_path / "changes" / "7.fixed.md").write_text("**A fix.** (#7)\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "fix")
    body = tmp_path / "body.md"
    body.write_text("Fixes #7\n")
    argv = ["check", "--base", "main", "--body", str(body), "--root", str(tmp_path)]
    assert changes.main(argv) == 0
    body.write_text("Fixes #8\n")
    assert changes.main(argv) == 1
    assert "issue #7 is not in the body's Fixes lines" in capsys.readouterr().out
