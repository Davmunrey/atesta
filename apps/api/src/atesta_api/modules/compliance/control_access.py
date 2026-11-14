"""Visibility of common controls reached from the published or local preview catalog."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.models import Control, Framework, Mapping, Requirement
from atesta_api.modules.compliance.scoring import active_frameworks


def control_is_visible(session: Session, key: str) -> bool:
    control = session.get(Control, key)
    if control is None or control.retired_at is not None:
        return False
    visible = [f.key for f in active_frameworks(session)]
    mapped = session.scalar(
        select(Mapping.control_key)
        .join(
            Requirement,
            (Requirement.framework_key == Mapping.framework_key)
            & (Requirement.code == Mapping.requirement_code),
        )
        .where(
            Mapping.control_key == key,
            Mapping.framework_key.in_(visible),
            Mapping.retired_at.is_(None),
            Requirement.retired_at.is_(None),
        )
        .limit(1)
    )
    if mapped is not None:
        return True
    return (
        session.scalar(
            select(Framework.key)
            .where(
                Framework.key.in_(visible),
                Framework.attributes.contains({"preparation_controls": [key]}),
            )
            .limit(1)
        )
        is not None
    )
