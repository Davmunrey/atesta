"""Vendored agent skills are byte-for-byte what was reviewed (ADR-013, issue #120).

.claude/skills/VENDORED.sha256 lists every vendored file; regenerate it only with a review:
git ls-files .claude/skills | grep -vE 'VENDORED\\.(md|sha256)$' | xargs shasum -a 256 | sort -k2
"""

import hashlib
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
SKILLS = ROOT / ".claude" / "skills"
OWN = {"VENDORED.md", "VENDORED.sha256"}
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


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


def frontmatter_problems(skill_md: Path) -> list[str]:
    """A skill loads only with a name and a description; a hook would run code (ADR-013)."""
    match = FRONTMATTER.match(skill_md.read_text())
    if match is None:
        return [f"no frontmatter: {skill_md.parent.name}"]
    meta = yaml.safe_load(match.group(1))
    problems = [
        f"no {key}: {skill_md.parent.name}"
        for key in ("name", "description")
        if not isinstance(meta.get(key), str) or not meta[key].strip()
    ]
    if "hooks" in meta:
        problems.append(f"declares hooks: {skill_md.parent.name}")
    return problems


def unrecorded(skills: Path, vendored_md: str) -> list[str]:
    """Skill directories with no row in VENDORED.md's table (first cell starts with the name)."""
    rows = {
        line.split("|")[1].strip().split(" ")[0]
        for line in vendored_md.splitlines()
        if line.startswith("| ")
    }
    return sorted(p.name for p in skills.iterdir() if p.is_dir() and p.name not in rows)


def test_every_vendored_skill_has_a_name_a_description_and_no_hooks() -> None:
    skills = sorted(SKILLS.glob("*/SKILL.md"))
    assert len(skills) == len([p for p in SKILLS.iterdir() if p.is_dir()])
    assert [problem for p in skills for problem in frontmatter_problems(p)] == []


def test_every_vendored_skill_has_a_row_in_vendored_md() -> None:
    assert unrecorded(SKILLS, (SKILLS / "VENDORED.md").read_text()) == []


def test_a_hook_a_missing_description_or_an_unrecorded_skill_is_caught(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    good = tmp_path / "a" / "SKILL.md"
    good.write_text("---\nname: a\ndescription: Use when testing\n---\n# a\n")
    bad = tmp_path / "b" / "SKILL.md"
    bad.write_text("---\nname: b\nhooks:\n  Stop: []\n---\n# b\n")
    assert frontmatter_problems(good) == []
    assert frontmatter_problems(bad) == ["no description: b", "declares hooks: b"]
    table = "| Skill | Source |\n|---|---|\n| a (text subset) | x |\n"
    assert unrecorded(tmp_path, table) == ["b"]
