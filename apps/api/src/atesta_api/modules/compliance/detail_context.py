"""Explicit public catalog fields; preparation has neither mappings nor observations."""

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.catalog_schema import PackContext
from atesta_api.modules.compliance.detail_schema import CheckReference, PreparationControl
from atesta_api.modules.compliance.models import Control
from atesta_api.modules.compliance.scoring import active_control_checks


def public_context[T: BaseModel](model: type[T], attributes: dict[str, object]) -> T | None:
    try:
        return model.model_validate(
            {k: v for k, v in attributes.items() if k in model.model_fields}
        )
    except ValidationError:
        # Legacy catalogs have no preparation metadata. Never expose arbitrary attributes.
        return None


def preparation_controls(session: Session, context: PackContext | None) -> list[PreparationControl]:
    if context is None or not context.preparation_controls:
        return []
    rows = session.scalars(
        select(Control).where(
            Control.key.in_(context.preparation_controls), Control.retired_at.is_(None)
        )
    )
    controls = {row.key: row for row in rows}
    checks = active_control_checks(session)
    return [
        PreparationControl(
            key=c.key,
            title_es=c.title_es,
            title_en=c.title_en,
            description_es=c.description_es,
            description_en=c.description_en,
            manual=c.manual,
            remediation_refs=c.remediation_refs,
            checks=[CheckReference(engine=e, check_id=i) for e, i in checks.get(c.key, [])],
        )
        for key in dict.fromkeys(context.preparation_controls)
        if (c := controls.get(key)) is not None
    ]
