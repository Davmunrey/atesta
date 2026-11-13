"""In CI, a missing test database URL fails the run instead of skipping DB tests."""

import os
import subprocess
import sys
from pathlib import Path


def test_ci_without_database_url_fails() -> None:
    env = {k: v for k, v in os.environ.items() if k != "ATESTA_TEST_DATABASE_URL"}
    env["CI"] = "true"
    health = Path(__file__).with_name("test_health.py")
    result = subprocess.run(  # noqa: S603  fixed argv, no shell
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(health)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "ATESTA_TEST_DATABASE_URL" in result.stderr + result.stdout


def test_ci_with_unreachable_database_url_errors_never_skips() -> None:
    env = dict(os.environ)
    env["CI"] = "true"
    env["ATESTA_TEST_DATABASE_URL"] = (
        "postgresql+psycopg://postgres@127.0.0.1:1/postgres?connect_timeout=2"
    )
    target = Path(__file__).with_name("db") / "test_rls.py"
    assert target.is_file()  # a rename must not make this test vacuous
    result = subprocess.run(  # noqa: S603  fixed argv, no shell
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(target)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout[-500:]  # ran and errored: not 4 or 5
    assert " error" in result.stdout
    assert "skipped" not in result.stdout
