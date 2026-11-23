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


def _release_root(tmp_path: Path, fragments: dict[str, str]) -> Path:
    (tmp_path / "changes").mkdir()
    (tmp_path / "changes" / "README.md").write_text("# Pending changes\n")
    for name, body in fragments.items():
        (tmp_path / "changes" / name).write_text(body)
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\nIntro.\n\n## Unreleased\n\nSee changes/.\n\n"
        "## v2026.10.1 (2026-10-01)\n\nOld.\n"
    )
    return tmp_path


def test_a_release_folds_fragments_by_kind_and_deletes_them(tmp_path: Path) -> None:
    from datetime import date

    root = _release_root(
        tmp_path,
        {
            "12.fixed.md": "**Fixed a thing.** (#12)\n",
            "10.added.md": "**Added a thing.** (#10)\n- detail one\n- detail two\n",
            "11.security.md": "**Hardened a thing.** (#11)\n",
            "9.added.md": "**Added earlier.** (#9)\n",
        },
    )
    names = changes.release(root, "v2026.11.1", date(2026, 11, 23))
    assert sorted(names) == ["10.added.md", "11.security.md", "12.fixed.md", "9.added.md"]
    text = (root / "CHANGELOG.md").read_text()
    new = text[text.index("## v2026.11.1") : text.index("## v2026.10.1")]
    assert new.splitlines()[0] == "## v2026.11.1 (2026-11-23)"
    assert new.index("### Added") < new.index("### Fixed") < new.index("### Security")
    assert new.index("**Added earlier.** (#9)") < new.index("**Added a thing.** (#10)")
    assert "  - detail one" in new
    assert text.index("## Unreleased") < text.index("## v2026.11.1") < text.index("## v2026.10.1")
    assert sorted(p.name for p in (root / "changes").iterdir()) == ["README.md"]


@pytest.mark.parametrize(
    ("version", "fragments", "message"),
    [
        ("2026.11.1", {"1.added.md": "**A.** (#1)\n"}, "version must look like"),
        ("v2026.10.1", {"1.added.md": "**A.** (#1)\n"}, "already in CHANGELOG.md"),
        ("v2026.11.1", {}, "no fragments"),
        ("v2026.11.1", {"1.added.md": "no bold sentence (#1)\n"}, "bold sentence"),
    ],
)
def test_a_release_refuses_bad_input(
    tmp_path: Path, version: str, fragments: dict[str, str], message: str
) -> None:
    from datetime import date

    root = _release_root(tmp_path, fragments)
    with pytest.raises(ValueError, match=message):
        changes.release(root, version, date(2026, 11, 23))
    assert sorted(p.name for p in (root / "changes").iterdir()) == sorted(["README.md", *fragments])
