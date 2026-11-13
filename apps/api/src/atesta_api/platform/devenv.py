"""Dev-only components fail closed outside a development environment (scanner-connectors spec)."""

import os

DEV_ENVS = frozenset({"local", "dev", "test"})


def require_dev(component: str) -> None:
    if os.environ.get("ATESTA_ENV") not in DEV_ENVS:
        raise RuntimeError(f"{component} is dev-only: ATESTA_ENV must be local, dev or test")
