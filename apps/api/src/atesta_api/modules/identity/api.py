"""Public interface of the identity module."""

import base64
import os
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from starlette.types import ASGIApp

from atesta_api.modules.identity.activity import is_member, person
from atesta_api.modules.identity.agent_oauth import (
    METADATA_PATH,
    AgentOAuth,
    AgentToken,
    grant_digest,
)
from atesta_api.modules.identity.api_tokens import (
    USAGE_RETENTION,
    ApiCaller,
    ApiTokenCaller,
    agent_oauth,
    annotate_scopes,
    as_agent,
    expire_key_usage,
    key_router,
    require_scope,
    token_labels,
)
from atesta_api.modules.identity.bff import (
    SessionCrypto,
    SessionEndedError,
    safe_return,
    session_ended_handler,
)
from atesta_api.modules.identity.bff import router as auth_router
from atesta_api.modules.identity.cognito import (
    AccessToken,
    CognitoOAuth,
    CognitoSettings,
    CognitoUserInfo,
    ExpiredTokenError,
    InvalidTokenError,
    ProviderUnavailableError,
    TokenSet,
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
from atesta_api.modules.identity.deps import (
    CurrentCaller,
    Member,
    OwnOrganization,
    member_read,
    own_organizations,
    require_member,
    require_role,
)
from atesta_api.modules.identity.erasure import (
    ErasureRefusedError,
    ErasureRun,
    due_erasure_requests,
    run_erasure_request,
)
from atesta_api.modules.identity.erasure_requests import (
    ApprovedErasure,
    ErasureStatus,
    ReceiptRow,
    approve_erasure,
    cancel_erasure,
    erasure_receipts,
    latest_erasure,
    request_erasure,
)
from atesta_api.modules.identity.for_operator import (
    PAGE_SIZE,
    SUSPENSION_REASONS,
    ApiKeyCounts,
    OperatorError,
    OrganizationFilters,
    OrganizationMetadata,
    OrganizationPage,
    api_key_counts,
    cancel_operator_closure,
    invitation_counts,
    last_activity,
    member_counts,
    organization_metadata,
    organization_rows,
    reactivate,
    start_operator_closure,
    suspend,
)
from atesta_api.modules.identity.invitations import QueryFreeRoute, normalize_email, token_hash
from atesta_api.modules.identity.models import Role
from atesta_api.modules.identity.org_profile import (
    OrganizationProfile,
    Recipient,
    organization_profile,
    recipients,
)
from atesta_api.modules.identity.routes import router
from atesta_api.modules.identity.staff import (
    STAFF_ROLES,
    StaffMember,
    StaffRole,
    add_staff,
    change_staff,
    enabled_admins,
    enabled_staff,
    staff_by_email,
    staff_list,
)
from atesta_api.modules.identity.standing import is_suspended


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
    app.state.agent_oauth = AgentOAuth.from_env(os.environ, settings.issuer, settings.app_client_id)


class _AgentAccess:
    """What the hosted MCP server needs for OAuth (mcp-oauth spec). The application state is
    read on every call: it is wired when the application starts, after the server is mounted."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    def _oauth(self) -> AgentOAuth | None:
        found: AgentOAuth | None = getattr(self._app.state, "agent_oauth", None)
        return found

    def challenge(self) -> str | None:
        oauth = self._oauth()
        return None if oauth is None else oauth.challenge()

    def verify(self, token: str) -> str | None:
        """The grant digest of a token issued for the hosted server, or None. Nothing about a
        refused token is logged or returned (rule 2)."""
        oauth = self._oauth()
        if oauth is None:
            return None
        verifier: TokenVerifier = self._app.state.token_verifier
        try:
            agent = verifier.verify_agent(token, oauth)
        except (InvalidTokenError, ExpiredTokenError, ProviderUnavailableError):
            return None
        return grant_digest(oauth.issuer, agent.client_id, agent.sub)

    def enter(self, api: ASGIApp, reference: str) -> ASGIApp:
        return as_agent(api, reference)


def agent_access(app: FastAPI) -> _AgentAccess:
    return _AgentAccess(app)


def protected_resource_metadata(request: Request, rest: str = "") -> dict[str, Any]:
    """Protected Resource Metadata of the hosted MCP server (RFC 9728, mcp-oauth spec): public,
    and 404 while OAuth is off. Served at the well-known path, with and without the resource's
    own path after it."""
    oauth = agent_oauth(request)
    if oauth is None or rest not in ("", urlsplit(oauth.resource).path.lstrip("/")):
        raise HTTPException(status_code=404, detail={"code": "identity.not_found"})
    return oauth.metadata()


def install_identity(app: FastAPI) -> None:
    """Routers and the handler that clears cookies when a session ends."""
    app.include_router(router)
    app.include_router(key_router)
    app.include_router(auth_router)
    app.add_exception_handler(SessionEndedError, session_ended_handler)
    # Outside the web app's contract: MCP clients read it, the console never does.
    for path in (METADATA_PATH, METADATA_PATH + "/{rest:path}"):
        app.add_api_route(
            path, protected_resource_metadata, methods=["GET"], include_in_schema=False
        )


__all__ = [
    "AgentOAuth",
    "AgentToken",
    # the operator service's staff sign-in (ADR-017, "Staff identity")
    "STAFF_ROLES",
    "AccessToken",
    "CognitoOAuth",
    "CognitoSettings",
    "ExpiredTokenError",
    "InvalidTokenError",
    "ProviderUnavailableError",
    "SessionCrypto",
    "StaffMember",
    "StaffRole",
    "TokenSet",
    "TokenVerifier",
    "enabled_staff",
    "change_staff",
    "staff_list",
    "add_staff",
    "enabled_admins",
    "staff_by_email",
    "ErasureStatus",
    "ErasureRefusedError",
    "ErasureRun",
    "due_erasure_requests",
    "run_erasure_request",
    "ReceiptRow",
    "erasure_receipts",
    "latest_erasure",
    "jwks_fetcher",
    "safe_return",
    "PAGE_SIZE",
    "SUSPENSION_REASONS",
    "USAGE_RETENTION",
    "ApiKeyCounts",
    "ApprovedErasure",
    "OperatorError",
    "OrganizationFilters",
    "OrganizationMetadata",
    "OrganizationPage",
    "api_key_counts",
    "approve_erasure",
    "cancel_erasure",
    "cancel_operator_closure",
    "invitation_counts",
    "last_activity",
    "member_counts",
    "organization_metadata",
    "organization_rows",
    "reactivate",
    "request_erasure",
    "start_operator_closure",
    "suspend",
    "ApiCaller",
    "agent_access",
    "agent_oauth",
    "annotate_scopes",
    "as_agent",
    "ApiTokenCaller",
    "ContextReason",
    "CurrentCaller",
    "Member",
    "OrganizationProfile",
    "OwnOrganization",
    "Recipient",
    "QueryFreeRoute",
    "Role",
    "ensure_dev_organization",
    "enter_invitation_context",
    "enter_org_context",
    "enter_training_link_context",
    "enter_user_context",
    "expire_key_usage",
    "grant_digest",
    "require_member",
    "require_role",
    "require_scope",
    "install_identity",
    "is_member",
    "is_suspended",
    "member_read",
    "normalize_email",
    "organization_profile",
    "own_organizations",
    "person",
    "recipients",
    "router",
    "token_hash",
    "token_labels",
    "wire_identity",
]
