"""Operator service settings (ADR-017, "Credentials, never shared").

Its own database credential and staff Cognito pool, read from `ATESTA_OPERATOR_*` and
`ATESTA_STAFF_*` names that the customer API and the worker never read. Startup refuses the
customer pool or app client, so a configuration slip cannot make customer tokens valid here.
"""

import base64
import os
from collections.abc import Mapping
from dataclasses import dataclass

from atesta_api.modules.identity.api import CognitoSettings
from atesta_api.platform.devenv import DEV_ENVS


@dataclass(frozen=True, slots=True)
class Settings:
    env: str
    database_url: str
    sslmode: str
    cognito: CognitoSettings
    web_origin: str  # the portal's own origin: OAuth redirects and the write-origin check
    session_key: bytes

    @property
    def dev(self) -> bool:
        return self.env in DEV_ENVS

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        environment = env.get("ATESTA_ENV", "")
        issuer = env.get("ATESTA_STAFF_COGNITO_ISSUER")
        base_url = env.get("ATESTA_STAFF_COGNITO_BASE_URL")
        if (issuer or base_url) and environment not in DEV_ENVS:
            raise RuntimeError(
                "staff Cognito issuer and base URL overrides require ATESTA_ENV local, dev or test"
            )
        cognito = CognitoSettings(
            env["ATESTA_STAFF_COGNITO_REGION"],
            env["ATESTA_STAFF_COGNITO_USER_POOL_ID"],
            env["ATESTA_STAFF_COGNITO_APP_CLIENT_ID"],
            env["ATESTA_STAFF_COGNITO_DOMAIN"],
            issuer,
            base_url,
        )
        if cognito.user_pool_id == env.get("ATESTA_COGNITO_USER_POOL_ID") or (
            cognito.app_client_id == env.get("ATESTA_COGNITO_APP_CLIENT_ID")
        ):
            raise RuntimeError("the operator service needs the staff pool, not the customer pool")
        key = base64.b64decode(env["ATESTA_OPERATOR_SESSION_KEY"])
        if key == base64.b64decode(env.get("ATESTA_SESSION_KEY", "")):
            raise RuntimeError("the operator session key must differ from the console's")
        return cls(
            environment,
            env["ATESTA_OPERATOR_DATABASE_URL"],
            env.get("ATESTA_DB_SSLMODE", "verify-full"),
            cognito,
            env["ATESTA_OPERATOR_WEB_ORIGIN"].rstrip("/"),
            key,
        )
