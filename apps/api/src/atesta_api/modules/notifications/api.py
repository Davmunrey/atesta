"""Public interface of the notifications module (ADR-008 amendment 1, notifications spec)."""

from fastapi import FastAPI

from atesta_api.modules.notifications.deliveries import claim_delivery
from atesta_api.modules.notifications.kinds import CRITICAL, OPTIONAL, Kind, receivable
from atesta_api.modules.notifications.mail import (
    FileMailer,
    Mailer,
    MemoryMailer,
    Message,
    UnsubscribeLinks,
    compose,
)
from atesta_api.modules.notifications.routes import public_router, router
from atesta_api.modules.notifications.tokens import TokenError, Unsubscribe, UnsubscribeTokens


def install_notifications(app: FastAPI) -> None:
    """Routes, and the unsubscribe key when ATESTA_NOTIFICATIONS_KEY is set (else links 503)."""
    app.state.notification_tokens = UnsubscribeTokens.from_env()
    app.include_router(router)
    app.include_router(public_router)


__all__ = [
    "CRITICAL",
    "OPTIONAL",
    "FileMailer",
    "Kind",
    "Mailer",
    "MemoryMailer",
    "Message",
    "TokenError",
    "Unsubscribe",
    "UnsubscribeLinks",
    "UnsubscribeTokens",
    "claim_delivery",
    "compose",
    "install_notifications",
    "receivable",
]
