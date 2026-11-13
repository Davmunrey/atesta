"""Scrub the Prowler log before it is kept for support (scanner-connectors spec, rule 2).

At ERROR, Prowler logs PowerShell stderr, which can echo the certificate command line, and the
Google provider can log credential material. Removed: every credential value and its base64
forms, JWT-shaped strings, PEM private key blocks (also with escaped newlines) and base64 runs
over 200 characters. Everything else stays, so the log is still useful.
"""

import base64
import re
from collections.abc import Iterable

REDACTED = "[REDACTED]"
_MIN_SECRET = 8  # shorter values would redact ordinary text
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*")
_BASE64_RUN = re.compile(r"[A-Za-z0-9+/_-]{201,}={0,2}")


def _forms(secret: str) -> set[str]:
    raw = secret.encode()
    standard = base64.b64encode(raw).decode()
    urlsafe = base64.urlsafe_b64encode(raw).decode()
    return {secret, standard, standard.rstrip("="), urlsafe, urlsafe.rstrip("=")}


def scrub(text: str, secrets: Iterable[str]) -> str:
    forms = {f for s in secrets if len(s) >= _MIN_SECRET for f in _forms(s)}
    for form in sorted(forms, key=len, reverse=True):  # longest first: no partial leftovers
        text = text.replace(form, REDACTED)
    for pattern in (_PEM, _JWT, _BASE64_RUN):
        text = pattern.sub(REDACTED, text)
    return text
