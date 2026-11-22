"""Changelog fragments (changes/README.md): validate the fragments a pull request adds.

Usage: python -m apps.api.devtools.changes check --base origin/main --body pr.md [--author x]
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
KINDS = ("added", "changed", "deprecated", "removed", "fixed", "security")
FRAGMENT = re.compile(r"^(\d+)(?:-(\d+))?\.(" + "|".join(KINDS) + r")\.md$")
FIXES = re.compile(
    r"\b(?:fix|fixes|fixed|close|closes|closed|resolve|resolves|resolved)\s+#(\d+)", re.I
)
EXEMPT_AUTHORS = {"dependabot[bot]"}
RELEASE = re.compile(r"^Release: v\d{4}\.\d{2}\.\d+$", re.M)


def fragment_problem(name: str, body: str) -> str | None:
    """Why this fragment is invalid, or None."""
    match = FRAGMENT.match(name)
    if match is None:
        return f"{name}: name must be <issue>.<kind>.md with kind in {', '.join(KINDS)}"
    issue = match.group(1)
    text = body.strip()
    if not re.match(r"^\*\*[^*\n]+\*\*", text):
        return f"{name}: must start with one bold sentence"
    if f"(#{issue})" not in text.splitlines()[0]:
        return f"{name}: first line must cite (#{issue})"
    if text.lstrip().startswith(("#", "- ")):
        return f"{name}: no headings or list markers"
    return None


def check(added: dict[str, str], changed: list[str], pr_body: str, author: str) -> list[str]:
    """Problems with a pull request's changelog entries; empty means it passes."""
    if author in EXEMPT_AUTHORS:
        return []
    problems: list[str] = []
    fixed = set(FIXES.findall(pr_body))
    if RELEASE.search(pr_body):
        return problems  # a release folds and deletes fragments; it adds none
    if "CHANGELOG.md" in changed:
        problems.append("CHANGELOG.md is edited only by a release; add a file in changes/")
    fragments = {name: body for name, body in added.items() if name != "README.md"}
    if not fragments:
        problems.append("add a fragment: changes/<issue>.<kind>.md (changes/README.md)")
    for name, body in sorted(fragments.items()):
        problem = fragment_problem(name, body)
        if problem:
            problems.append(problem)
            continue
        match = FRAGMENT.match(name)
        if match and match.group(1) not in fixed:
            problems.append(f"{name}: issue #{match.group(1)} is not in the body's Fixes lines")
    return problems


def _git(root: Path, *args: str) -> str:
    command = ["git", *args]  # git from PATH, as in CI; arguments are fixed, never user text
    result = subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)  # noqa: S603
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check"])
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--body", type=Path, required=True)
    parser.add_argument("--author", default="")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root: Path = args.root
    diff = _git(root, "diff", "--name-status", f"{args.base}...HEAD").splitlines()
    # Paths modified or deleted; creating CHANGELOG.md (this check's own bootstrap) is allowed.
    changed = [line.split("\t")[-1] for line in diff if not line.startswith("A")]
    added = {
        Path(path).name: (root / path).read_text()
        for status, *_, path in (line.split("\t") for line in diff)
        if status.startswith("A") and path.startswith("changes/")
    }
    problems = check(added, changed, args.body.read_text(), args.author)
    for problem in problems:
        print(f"FAILED {problem}")
    if not problems:
        count = len([name for name in added if name != "README.md"])
        print(f"passed: {count} changelog fragment(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
