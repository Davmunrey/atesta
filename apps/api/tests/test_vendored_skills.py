"""Vendored agent skills are byte-for-byte what was reviewed (ADR-013, issue #120).

.claude/skills/VENDORED.sha256 lists every vendored file; regenerate it only with a review:
git ls-files .claude/skills | grep -vE 'VENDORED\\.(md|sha256)$' | xargs shasum -a 256 | sort -k2
"""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILLS = ROOT / ".claude" / "skills"
OWN = {"VENDORED.md", "VENDORED.sha256"}


def drift(skills: Path, manifest: str) -> list[str]:
    expected = {}
    for line in manifest.splitlines():
        digest, path = line.split(maxsplit=1)
        expected[path] = digest
    root = skills.parent.parent
    actual = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in skills.rglob("*")
        if p.is_file() and p.name not in OWN and "__pycache__" not in p.parts
    }
    problems = [f"changed: {p}" for p in expected if p in actual and actual[p] != expected[p]]
    problems += [f"missing: {p}" for p in expected if p not in actual]
    problems += [f"unlisted: {p}" for p in actual if p not in expected]
    return sorted(problems)


def test_vendored_skills_match_the_manifest() -> None:
    assert drift(SKILLS, (SKILLS / "VENDORED.sha256").read_text()) == []


def test_an_edited_added_or_removed_file_is_caught(tmp_path: Path) -> None:
    skills = tmp_path / ".claude" / "skills"
    (skills / "a").mkdir(parents=True)
    (skills / "a" / "SKILL.md").write_text("reviewed")
    (skills / "a" / "gone.md").write_text("x")
    digest = hashlib.sha256(b"reviewed").hexdigest()
    gone = hashlib.sha256(b"x").hexdigest()
    manifest = f"{digest}  .claude/skills/a/SKILL.md\n{gone}  .claude/skills/a/gone.md\n"
    assert drift(skills, manifest) == []
    (skills / "a" / "SKILL.md").write_text("edited")
    (skills / "a" / "gone.md").unlink()
    (skills / "a" / "new.md").write_text("y")
    assert drift(skills, manifest) == [
        "changed: .claude/skills/a/SKILL.md",
        "missing: .claude/skills/a/gone.md",
        "unlisted: .claude/skills/a/new.md",
    ]
