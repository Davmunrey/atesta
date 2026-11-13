"""Static guards for pool safety, single engine factory and immutable migrations."""

import re
from pathlib import Path

API = Path(__file__).resolve().parents[1]
SRC = API / "src" / "atesta_api"
CODE = [*SRC.rglob("*.py"), *(API / "migrations").rglob("*.py")]

FORBIDDEN = {
    "session-level app.* setting": re.compile(
        r"SET\s+(SESSION\s+)?app\.|-c\s*app\.|(ALTER\s+(ROLE|DATABASE)[^\n]*SET\s+app\.)", re.I
    ),
    "set_config with is_local false": re.compile(r"set_config\([^)]*false", re.I),
    "bare Depends(get_db)": re.compile(r"Depends\(get_db\)"),
}


def _hits(pattern: re.Pattern[str], files: list[Path]) -> list[str]:
    return [f.name for f in files if pattern.search(f.read_text())]


def test_no_forbidden_patterns() -> None:
    found = {name: _hits(p, CODE) for name, p in FORBIDDEN.items()}
    assert found == dict.fromkeys(FORBIDDEN, [])


def test_only_tenancy_writes_settings() -> None:
    assert _hits(re.compile(r"set_config\("), CODE) == ["tenancy.py"]


def test_only_db_module_creates_engines() -> None:
    assert _hits(re.compile(r"\bcreate_engine\("), CODE) == ["db.py"]
