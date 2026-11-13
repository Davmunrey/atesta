import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """DB isolation tests may skip locally, never in CI (tenant-data-layer spec)."""
    if os.environ.get("CI") == "true" and not os.environ.get("ATESTA_TEST_DATABASE_URL"):
        raise pytest.UsageError("CI requires ATESTA_TEST_DATABASE_URL; DB tests must not skip")
