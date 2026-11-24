"""OAuth 2.1 for the hosted MCP server (mcp-oauth spec, ADR-016 amendment 1, issue 354).

The Cognito user pool is the authorization server; Atesta issues no token. A token proves a
person at an approved client. What that agent may do comes from a grant an admin recorded in
Atesta: an `api_tokens` row of kind `oauth`, found by the digest below.
"""

import hashlib
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

_RESOURCE = "ATESTA_MCP_RESOURCE_URL"
_CLIENTS = "ATESTA_MCP_OAUTH_CLIENTS"
_CLIENT_ID = re.compile(r"^[A-Za-z0-9_+.-]{1,128}$")
METADATA_PATH = "/.well-known/oauth-protected-resource"


@dataclass(frozen=True, slots=True)
class AgentToken:
    """A verified access token of the hosted MCP server: who, and through which client."""

    sub: str
    client_id: str


@dataclass(frozen=True, slots=True)
class AgentOAuth:
    resource: str  # the hosted MCP server's canonical URL, and the token's audience
    issuer: str  # the Cognito user pool
    clients: Mapping[str, str]  # approved client id -> display name

    @property
    def scope(self) -> str:
        """The one scope a token must carry. Permissions come from the grant, not from it."""
        return f"{self.resource}/agent"

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] = os.environ, issuer: str = "", web_client_id: str = ""
    ) -> "AgentOAuth | None":
        """None unless the hosted server, its URL and at least one client are configured.

        ValueError, so the API does not start, on a malformed value.
        """
        resource, listed = env.get(_RESOURCE, ""), env.get(_CLIENTS, "")
        if env.get("ATESTA_MCP_REMOTE") != "1" or not resource or not listed:
            return None
        url = urlsplit(resource)
        if (
            url.scheme != "https"
            or not url.netloc
            or url.query
            or url.fragment
            or "#" in resource
            or resource.endswith("/")
        ):
            raise ValueError(f"{_RESOURCE} must be an https URL with no query, fragment or final /")
        clients: dict[str, str] = {}
        for entry in listed.split(","):
            client_id, _, name = (part.strip() for part in entry.partition("="))
            if not _CLIENT_ID.fullmatch(client_id) or not name or client_id in clients:
                raise ValueError(f"{_CLIENTS} must be a list of distinct client_id=Name pairs")
            if client_id == web_client_id:
                raise ValueError(f"{_CLIENTS} must not list the web app's own client")
            clients[client_id] = name
        return cls(resource, issuer, clients)

    def metadata(self) -> dict[str, Any]:
        """Protected Resource Metadata (RFC 9728)."""
        return {
            "resource": self.resource,
            "authorization_servers": [self.issuer],
            "scopes_supported": [self.scope],
            "bearer_methods_supported": ["header"],
            "resource_name": "Atesta",
        }

    def challenge(self) -> str:
        """The WWW-Authenticate value of a 401 from the hosted server."""
        url = urlsplit(self.resource)
        metadata = f"{url.scheme}://{url.netloc}{METADATA_PATH}{url.path}"
        return f'Bearer resource_metadata="{metadata}", scope="{self.scope}"'


def grant_digest(issuer: str, client_id: str, sub: str) -> str:
    """What a grant is found by: the verified issuer, client and person, never a secret.

    Lengths are part of the input, so no field can run into the next.
    """
    parts = ("oauth", issuer, client_id, sub)
    joined = "".join(f"{len(part)}:{part}\n" for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
