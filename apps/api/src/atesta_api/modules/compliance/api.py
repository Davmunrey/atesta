"""Public interface of the compliance module."""

from fastapi import FastAPI

from atesta_api.modules.compliance.fixtures import load_catalog_fixture
from atesta_api.modules.compliance.scoring import (
    FrameworkInfo,
    active_control_checks,
    active_control_keys,
    active_frameworks,
    control_is_active,
    include_drafts,
    scoreable_framework_keys,
    snapshot_framework,
)


def install_compliance(app: FastAPI) -> None:
    # Read routes compose module APIs; import after those interfaces are initialized.
    from atesta_api.modules.compliance.detail import router as detail_router
    from atesta_api.modules.compliance.overview import router

    app.include_router(router)
    app.include_router(detail_router)


__all__ = [
    "FrameworkInfo",
    "active_control_checks",
    "active_control_keys",
    "active_frameworks",
    "control_is_active",
    "include_drafts",
    "install_compliance",
    "load_catalog_fixture",
    "scoreable_framework_keys",
    "snapshot_framework",
]
