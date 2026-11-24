"""Where email goes and who it comes from (notifications spec; issue 386).

Configured once per process: the worker from its environment, tests with a MemoryMailer. With
no configuration every delivery ends `suppressed` and nothing is sent.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from atesta_api.modules.notifications.mail import FileMailer, Mailer
from atesta_api.modules.notifications.tokens import UnsubscribeTokens


@dataclass(frozen=True, slots=True)
class MailConfig:
    mailer: Mailer
    sender_address: str  # ATESTA_MAIL_FROM; the display name is "Atesta · <organization>"
    web_base_url: str
    tokens: UnsubscribeTokens | None  # without a key, optional email is not sent


_config: MailConfig | None = None


def configure_mail(config: MailConfig | None) -> None:
    global _config  # noqa: PLW0603 - one process-wide setting, set at start-up
    _config = config


def mail_config() -> MailConfig | None:
    return _config


def mail_config_from_env(env: Mapping[str, str] = os.environ) -> MailConfig | None:
    """Local development writes .eml files (ATESTA_MAIL_DIR); SES arrives with PR 4."""
    directory, sender, web = (
        env.get("ATESTA_MAIL_DIR"),
        env.get("ATESTA_MAIL_FROM"),
        env.get("ATESTA_WEB_BASE_URL"),
    )
    if not (directory and sender and web):
        return None
    return MailConfig(
        mailer=FileMailer(Path(directory)),
        sender_address=sender,
        web_base_url=web.rstrip("/"),
        tokens=UnsubscribeTokens.from_env(env),
    )
