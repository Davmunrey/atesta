"""Mi trabajo (rbac spec): the measures assigned to the signed-in person, across frameworks.

Reads the same append-only rows as the register: the latest assignment and the latest
assessment of each measure. Titles come from the catalog; free text is never returned here.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from atesta_api.modules.compliance.register import (
    Applicability,
    Implementation,
    _assessments,
    _assignments,
    _requirements,
)
from atesta_api.modules.compliance.scoring import active_frameworks
from atesta_api.modules.identity.api import Member, Role, require_role
from atesta_api.platform.db import DbSession

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["compliance"])


class MyWorkItem(BaseModel):
    framework_key: str
    framework_name: str
    code: str
    title_es: str
    title_en: str | None
    due_on: date | None
    applicability: Applicability | None
    implementation: Implementation | None


@router.get("/my-work")
def my_work(
    member: Annotated[Member, Depends(require_role(Role.MEMBER))], session: DbSession
) -> list[MyWorkItem]:
    items: list[MyWorkItem] = []
    for framework in active_frameworks(session):
        assigned = {
            code: a
            for code, a in _assignments(session, member.organization_id, framework.key).items()
            if a.owner_user_id == member.user_id
        }
        if not assigned:
            continue
        assessed = _assessments(session, member.organization_id, framework.key)
        for requirement in _requirements(session, framework.key):
            assignment = assigned.get(requirement.code)
            if assignment is None:
                continue
            latest = assessed.get(requirement.code)
            items.append(
                MyWorkItem(
                    framework_key=framework.key,
                    framework_name=framework.name,
                    code=requirement.code,
                    title_es=requirement.title_es,
                    title_en=requirement.title_en,
                    due_on=assignment.due_on,
                    applicability=latest.applicability if latest else None,
                    implementation=latest.implementation if latest else None,
                )
            )
    items.sort(key=lambda i: (i.due_on is None, i.due_on or date.max, i.framework_key, i.code))
    return items
