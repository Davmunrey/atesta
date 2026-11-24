"""One-click unsubscribe tokens (notifications spec, PR 1; ADR-012 amendment 7).

Sealed with AES-GCM under ATESTA_NOTIFICATIONS_KEY and bound to the name `unsubscribe`: the token
hides who and what it names, and a token sealed for anything else does not open. The worker
issues them, so it holds this key and never the session-cookie key.
"""

import base64
import binascii
import json
import os
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from atesta_api.modules.notifications.kinds import CRITICAL, Kind

NAME = b"unsubscribe"
LIFETIME = timedelta(days=60)
_NONCE = 12


class TokenError(Exception):
    """The token does not open, names no valid type, or is too old."""


@dataclass(frozen=True, slots=True)
class Unsubscribe:
    organization_id: uuid.UUID
    user_id: uuid.UUID
    kind: Kind


class UnsubscribeTokens:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("the notifications key must be 32 bytes")
        self._aead = AESGCM(key)

    @classmethod
    def from_env(cls) -> "UnsubscribeTokens | None":
        raw = os.environ.get("ATESTA_NOTIFICATIONS_KEY")
        return cls(base64.b64decode(raw)) if raw else None

    def issue(
        self, organization_id: uuid.UUID, user_id: uuid.UUID, kind: Kind, *, today: date
    ) -> str:
        if kind in CRITICAL:
            raise ValueError(f"no unsubscribe token for the critical type {kind}")
        payload = {
            "o": str(organization_id),
            "u": str(user_id),
            "k": kind.value,
            "d": today.isoformat(),
        }
        nonce = os.urandom(_NONCE)
        sealed = nonce + self._aead.encrypt(nonce, json.dumps(payload).encode(), NAME)
        return base64.urlsafe_b64encode(sealed).decode().rstrip("=")

    def open(self, token: str, *, today: date) -> Unsubscribe:
        try:
            raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            data = json.loads(self._aead.decrypt(raw[:_NONCE], raw[_NONCE:], NAME))
            issued = date.fromisoformat(data["d"])
            opened = Unsubscribe(uuid.UUID(data["o"]), uuid.UUID(data["u"]), Kind(data["k"]))
        except (InvalidTag, ValueError, KeyError, TypeError, binascii.Error):
            raise TokenError("invalid unsubscribe token") from None
        if opened.kind in CRITICAL or not issued <= today <= issued + LIFETIME:
            raise TokenError("expired or not optional")
        return opened
