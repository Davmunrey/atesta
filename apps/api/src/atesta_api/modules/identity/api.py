"""Public interface of the identity module."""

import base64
import os

import httpx
from fastapi import FastAPI

from atesta_api.modules.identity.activity import is_member, person
from atesta_api.modules.identity.api_tokens import (
    ApiCaller,
    ApiTokenCaller,
    key_router,
    require_scope,
)
from atesta_api.modules.identity.bff import SessionCrypto, SessionEndedError, session_ended_handler
from atesta_api.modules.identity.bff import router as auth_router
from atesta_api.modules.identity.cognito import (
    CognitoOAuth,
    CognitoSettings,
    CognitoUserInfo,
    TokenVerifier,
    jwks_fetcher,
)
from atesta_api.modules.identity.context import (
    ContextReason,
    ensure_dev_organization,
    enter_invitation_context,
    enter_org_context,
    enter_training_link_context,
    enter_user_context,
)
from atesta_api.modules.identity.deps import CurrentCaller, Member, require_member, require_role
from atesta_api.modules.identity.invitations import QueryFreeRoute, normalize_email, token_hash
from atesta_api.modules.identity.models import Role
from atesta_api.modules.identity.routes import router


def wire_identity(app: FastAPI, client: httpx.Client) -> None:
    settings = CognitoSettings.from_env()
    web_origin = os.environ["ATESTA_WEB_ORIGIN"].rstrip("/")
    verifier = TokenVerifier(settings, jwks_fetcher(settings, client))
    app.state.token_verifier = verifier
    app.state.identity_provider = CognitoUserInfo(settings, client)
    app.state.web_base_url = os.environ["ATESTA_WEB_BASE_URL"].rstrip("/")
    app.state.web_origin = web_origin
    app.state.session_crypto = SessionCrypto(base64.b64decode(os.environ["ATESTA_SESSION_KEY"]))
    app.state.oauth = CognitoOAuth(settings, client, verifier, web_origin)


def install_identity(app: FastAPI) -> None:
    """Routers and the handler that clears cookies when a session ends."""
    app.include_router(router)
    app.include_router(key_router)
    app.include_router(auth_router)
    app.add_exception_handler(SessionEndedError, session_ended_handler)


__all__ = [
    "ApiCaller",
    "ApiTokenCaller",
    "ContextReason",
    "CurrentCaller",
    "Member",
    "QueryFreeRoute",
    "Role",
    "ensure_dev_organization",
    "enter_invitation_context",
    "enter_org_context",
    "enter_training_link_context",
    "enter_user_context",
    "require_member",
    "require_role",
    "require_scope",
    "install_identity",
    "is_member",
    "normalize_email",
    "person",
    "router",
    "token_hash",
    "wire_identity",
]
