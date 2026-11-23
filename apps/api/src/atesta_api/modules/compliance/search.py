"""Global search over the requirements an organization may see (console-shell spec).

Catalog content only, never tenant rows. Matching ignores case and accents, in Python over the
active frameworks' requirements (a few hundred rows), so no database extension is needed.
"""

import unicodedata
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from atesta_api.modules.compliance.register import _requirements
from atesta_api.modules.compliance.scoring import active_frameworks
from atesta_api.modules.identity.api import Member, require_member
from atesta_api.platform.db import DbSession

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["compliance"])
LIMIT = 12


class SearchResult(BaseModel):
    framework_key: str
    framework_name: str
    code: str
    title_es: str
    title_en: str | None


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@router.get("/search")
def search(
    q: Annotated[str, Query(min_length=2, max_length=100)],
    member: Annotated[Member, Depends(require_member)],
    session: DbSession,
) -> list[SearchResult]:
    _ = member  # membership is the gate; results are catalog content
    words = _plain(q).split()
    found: list[SearchResult] = []
    for framework in active_frameworks(session):
        for r in _requirements(session, framework.key):
            haystack = _plain(f"{r.code} {r.title_es} {r.title_en or ''}")
            if all(word in haystack for word in words):
                found.append(
                    SearchResult(
                        framework_key=framework.key,
                        framework_name=framework.name,
                        code=r.code,
                        title_es=r.title_es,
                        title_en=r.title_en,
                    )
                )
                if len(found) == LIMIT:
                    return found
    return found
