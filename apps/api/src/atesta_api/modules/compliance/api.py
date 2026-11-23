"""Public interface of the compliance module."""

from fastapi import FastAPI

from atesta_api.modules.compliance.catalog import read_catalog
from atesta_api.modules.compliance.catalog_preview import import_preview
from atesta_api.modules.compliance.control_access import control_is_visible
from atesta_api.modules.compliance.fixtures import load_catalog_fixture
from atesta_api.modules.compliance.scoring import (
    FrameworkInfo,
    active_control_checks,
    active_control_keys,
    active_frameworks,
    control_is_active,
    include_drafts,
    reviewed_control_results,
    scoreable_framework_keys,
    snapshot_chain_tip,
    snapshot_framework,
)


def install_compliance(app: FastAPI) -> None:
    # Read routes compose module APIs; import after those interfaces are initialized.
    from atesta_api.modules.compliance.detail import router as detail_router
    from atesta_api.modules.compliance.incidents import router as incidents_router
    from atesta_api.modules.compliance.my_work import router as my_work_router
    from atesta_api.modules.compliance.overview import router
    from atesta_api.modules.compliance.readiness import router as readiness_router
    from atesta_api.modules.compliance.register import router as register_router
    from atesta_api.modules.compliance.reviews import router as reviews_router
    from atesta_api.modules.compliance.routines import router as routines_router
    from atesta_api.modules.compliance.search import router as search_router
    from atesta_api.modules.compliance.training import public_router as training_link_router
    from atesta_api.modules.compliance.training import router as training_router

    app.include_router(router)
    app.include_router(detail_router)
    app.include_router(reviews_router)
    app.include_router(register_router)
    app.include_router(my_work_router)
    app.include_router(readiness_router)
    app.include_router(search_router)
    app.include_router(routines_router)
    app.include_router(training_router)
    app.include_router(training_link_router)
    app.include_router(incidents_router)


__all__ = [
    "FrameworkInfo",
    "active_control_checks",
    "active_control_keys",
    "active_frameworks",
    "control_is_active",
    "control_is_visible",
    "include_drafts",
    "import_preview",
    "install_compliance",
    "load_catalog_fixture",
    "read_catalog",
    "reviewed_control_results",
    "scoreable_framework_keys",
    "snapshot_chain_tip",
    "snapshot_framework",
]
