"""`GET /api/v1/me`: who is signed in to the operator service, and as what."""

from atesta_api.modules.identity.api import StaffRole
from fastapi import APIRouter
from pydantic import BaseModel

from atesta_operator.auth import CurrentStaff

router = APIRouter(prefix="/api/v1", tags=["staff"])


class MeOut(BaseModel):
    email: str
    role: StaffRole


@router.get("/me")
def me(staff: CurrentStaff) -> MeOut:
    return MeOut(email=staff.email, role=staff.role)
