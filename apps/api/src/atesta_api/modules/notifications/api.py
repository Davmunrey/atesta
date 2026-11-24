"""Public interface of the notifications module (ADR-008 amendment 1, notifications spec)."""

from fastapi import FastAPI

from atesta_api.modules.notifications.clocks import (
    ClockTiming,
    IncidentClocks,
    due_milestones,
    notices_due,
    schedule_clock_notices,
    send_clock_notices,
)
from atesta_api.modules.notifications.config import (
    MailConfig,
    configure_mail,
    mail_config,
    mail_config_from_env,
)
from atesta_api.modules.notifications.deliveries import claim_delivery
from atesta_api.modules.notifications.digest import (
    DAILY_TASK,
    DueItem,
    WeeklyFacts,
    defer_daily,
    is_send_slot,
    next_daily_run,
    notice_days,
    send_due_digest,
    send_weekly_summary,
)
from atesta_api.modules.notifications.events import NOTIFIABLE, handle_event, queue_event
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
    "DAILY_TASK",
    "DueItem",
    "WeeklyFacts",
    "NOTIFIABLE",
    "ClockTiming",
    "IncidentClocks",
    "MailConfig",
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
    "configure_mail",
    "defer_daily",
    "due_milestones",
    "handle_event",
    "is_send_slot",
    "install_notifications",
    "mail_config",
    "mail_config_from_env",
    "next_daily_run",
    "notice_days",
    "notices_due",
    "queue_event",
    "receivable",
    "schedule_clock_notices",
    "send_clock_notices",
    "send_due_digest",
    "send_weekly_summary",
]
