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
