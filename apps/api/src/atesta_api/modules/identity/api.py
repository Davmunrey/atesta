"""Public interface of the identity module."""

import os

import httpx
from fastapi import FastAPI

from atesta_api.modules.identity.cognito import (
    CognitoSettings,
    CognitoUserInfo,
    TokenVerifier,
    jwks_fetcher,
)
from atesta_api.modules.identity.context import (
    ContextReason,
    enter_invitation_context,
    enter_org_context,
    enter_user_context,
)
from atesta_api.modules.identity.deps import CurrentCaller, Member, require_member, require_role
from atesta_api.modules.identity.models import Role
from atesta_api.modules.identity.routes import router


def wire_identity(app: FastAPI, client: httpx.Client) -> None:
    settings = CognitoSettings.from_env()
    app.state.token_verifier = TokenVerifier(settings, jwks_fetcher(settings, client))
    app.state.identity_provider = CognitoUserInfo(settings, client)
    app.state.web_base_url = os.environ["ATESTA_WEB_BASE_URL"].rstrip("/")


__all__ = [
    "ContextReason",
    "CurrentCaller",
    "Member",
    "Role",
    "enter_invitation_context",
    "enter_org_context",
    "enter_user_context",
    "require_member",
    "require_role",
    "router",
    "wire_identity",
]
