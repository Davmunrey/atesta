"""Changelog fragments (changes/README.md): validate the fragments a pull request adds.

Usage:
    python -m apps.api.devtools.changes check --base origin/main --body pr.md [--author x]
    python -m apps.api.devtools.changes release --version v2026.11.1

`release` folds every fragment into CHANGELOG.md under the version, grouped by kind in the
order of KINDS, and deletes the fragments; the release pull request's body carries
`Release: <version>` so the `check` job lets it edit CHANGELOG.md.
"""

import argparse
import re
import subprocess
import sys
from datetime import date
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


VERSION = re.compile(r"^v\d{4}\.\d{2}\.\d+$")


def release(root: Path, version: str, today: date) -> list[str]:
    """Fold the fragments into CHANGELOG.md under `version`; return the fragment names."""
    if not VERSION.match(version):
        raise ValueError(f"version must look like v2026.11.1, got {version!r}")
    changelog = root / "CHANGELOG.md"
    text = changelog.read_text()
    if f"\n## {version} " in text:
        raise ValueError(f"{version} is already in CHANGELOG.md")
    paths = sorted(p for p in (root / "changes").glob("*.md") if p.name != "README.md")
    if not paths:
        raise ValueError("no fragments to release")
    problems = [p for p in (fragment_problem(x.name, x.read_text()) for x in paths) if p]
    if problems:
        raise ValueError("; ".join(problems))

    kinds: dict[Path, tuple[int, int, int]] = {}
    for path in paths:
        match = FRAGMENT.match(path.name)
        if match is None:  # unreachable after fragment_problem, kept for the type checker
            raise ValueError(f"{path.name}: not a fragment name")
        kinds[path] = (KINDS.index(match.group(3)), int(match.group(1)), int(match.group(2) or 1))
    section = [f"## {version} ({today.isoformat()})", ""]
    for index, kind in enumerate(KINDS):
        entries = sorted((p for p in paths if kinds[p][0] == index), key=kinds.__getitem__)
        if not entries:
            continue
        section += [f"### {kind.capitalize()}", ""]
        for path in entries:
            first, *rest = path.read_text().strip().splitlines()
            section.append(f"- {first}")
            section += [f"  {line}" if line else "" for line in rest]
        section.append("")
    unreleased = text.index("## Unreleased")
    following = text.find("\n## ", unreleased + 1)
    cut = len(text) if following == -1 else following + 1
    head = text[:cut].rstrip("\n") + "\n\n"
    changelog.write_text(
        head + "\n".join(section).rstrip("\n") + "\n" + ("\n" + text[cut:] if text[cut:] else "")
    )
    for path in paths:
        path.unlink()
    return [p.name for p in paths]


def _git(root: Path, *args: str) -> str:
    command = ["git", *args]  # git from PATH, as in CI; arguments are fixed, never user text
    result = subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)  # noqa: S603 - fixed args
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "release"])
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--body", type=Path)
    parser.add_argument("--author", default="")
    parser.add_argument("--version")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root: Path = args.root
    if args.command == "release":
        if not args.version:
            parser.error("release needs --version")
        names = release(root, args.version, date.today())
        print(f"released {args.version}: {len(names)} fragment(s) folded into CHANGELOG.md")
        return 0
    if args.body is None:
        parser.error("check needs --body")
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
