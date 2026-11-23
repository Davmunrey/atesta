"""Every route under /frameworks/{framework_key} opens only a framework the plan grants.

billing-entitlements spec: membership first (a non-member gets 404), then an unknown framework
keeps its 404, then billing decides (403 billing.plan_limit). The plan is billing's (ADR-009).
"""

from typing import Annotated

from fastapi import Depends, HTTPException

from atesta_api.modules.billing.api import require_framework
from atesta_api.modules.compliance.scoring import active_frameworks
from atesta_api.modules.identity.api import Member, require_member
from atesta_api.platform.db import DbSession


def framework_in_plan(
    framework_key: str, member: Annotated[Member, Depends(require_member)], session: DbSession
) -> None:
    if framework_key not in {f.key for f in active_frameworks(session)}:
        raise HTTPException(404, detail={"code": "compliance.not_found"})
    require_framework(session, member.organization_id, framework_key)
