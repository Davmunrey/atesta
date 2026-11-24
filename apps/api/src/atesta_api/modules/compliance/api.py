"""Public interface of the compliance module."""

import uuid
from datetime import date
from typing import TYPE_CHECKING

from fastapi import FastAPI
from sqlalchemy.orm import Session

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

if TYPE_CHECKING:
    from atesta_api.modules.compliance.due import ComplianceWeek
    from atesta_api.modules.notifications.api import DueItem, IncidentClocks


def incident_clocks(
    session: Session, org: uuid.UUID, incident_id: uuid.UUID
) -> "IncidentClocks | None":
    """One incident's reporting clocks, for the notify_clock job (notifications spec PR 2)."""
    # Lazy, like the routers below: incidents imports module APIs initialized after this one.
    from atesta_api.modules.compliance.incidents import incident_clocks as read  # noqa: PLC0415 - see above

    return read(session, org, incident_id)


def due_items(session: Session, org: uuid.UUID, dates: frozenset[date]) -> "list[DueItem]":
    """Items due on exactly these dates, for the daily digest (notifications spec PR 3)."""
    # Lazy, like incident_clocks: due reads the overview, which composes other module APIs.
    from atesta_api.modules.compliance.due import due_items as read  # noqa: PLC0415 - see above

    return read(session, org, dates)


def weekly_compliance(session: Session, org: uuid.UUID, *, today: date) -> "ComplianceWeek":
    """Scores and due counts for the weekly summary (notifications spec PR 3)."""
    from atesta_api.modules.compliance.due import weekly_compliance as read  # noqa: PLC0415 - lazy, see due_items

    return read(session, org, today=today)


def install_compliance(app: FastAPI) -> None:
    # Read routes compose module APIs; import after those interfaces are initialized.
    from atesta_api.modules.compliance.detail import router as detail_router
    from atesta_api.modules.compliance.dossier import router as dossier_router
    from atesta_api.modules.compliance.incidents import router as incidents_router
    from atesta_api.modules.compliance.my_work import router as my_work_router
    from atesta_api.modules.compliance.overview import router
    from atesta_api.modules.compliance.proposals import router as proposals_router
    from atesta_api.modules.compliance.proposals import token_router as proposals_token_router
    from atesta_api.modules.compliance.readiness import router as readiness_router
    from atesta_api.modules.compliance.register import router as register_router
    from atesta_api.modules.compliance.report import router as report_router
    from atesta_api.modules.compliance.reviews import router as reviews_router
    from atesta_api.modules.compliance.routines import router as routines_router
    from atesta_api.modules.compliance.search import router as search_router
    from atesta_api.modules.compliance.token_routes import router as token_router
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
    app.include_router(dossier_router)
    app.include_router(report_router)
    app.include_router(token_router)
    app.include_router(proposals_router)
    app.include_router(proposals_token_router)


__all__ = [
    "FrameworkInfo",
    "active_control_checks",
    "active_control_keys",
    "active_frameworks",
    "control_is_active",
    "control_is_visible",
    "include_drafts",
    "due_items",
    "incident_clocks",
    "weekly_compliance",
    "import_preview",
    "install_compliance",
    "load_catalog_fixture",
    "read_catalog",
    "reviewed_control_results",
    "scoreable_framework_keys",
    "snapshot_chain_tip",
    "snapshot_framework",
]
