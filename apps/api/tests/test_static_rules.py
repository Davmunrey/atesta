"""Static guards for pool safety, single engine factory and immutable migrations."""

import re
from pathlib import Path

API = Path(__file__).resolve().parents[1]
APPS = API.parent
_EXTENSIONS = ("*.py", "*.sql", "*.sh", "*.ts", "*.tsx", "*.js", "*.mjs")
_SKIP = {"tests", "node_modules", ".venv", "__pycache__", ".next", "out"}


def _code(root: Path) -> list[Path]:
    """Every source file under root; exclusions match path parts relative to root."""
    files = (f for ext in _EXTENSIONS for f in root.rglob(ext))
    return sorted(f for f in files if not _SKIP.intersection(f.relative_to(root).parts))


CODE = _code(APPS)

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


def test_scan_covers_sql_and_worker_code(tmp_path: Path) -> None:
    (tmp_path / "worker").mkdir()
    (tmp_path / "worker" / "jobs.py").write_text('session.execute(text("SET app.x = 1"))\n')
    (tmp_path / "setup.sql").write_text("ALTER ROLE atesta_app SET app.organization_id = 'x';\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "skipped.py").write_text('"SET app.x"\n')
    files = _code(tmp_path)
    assert [f.name for f in files] == ["setup.sql", "jobs.py"]
    pattern = FORBIDDEN["session-level app.* setting"]
    assert _hits(pattern, files) == ["setup.sql", "jobs.py"]
    assert any(f.name == "bootstrap.sql" for f in CODE)
