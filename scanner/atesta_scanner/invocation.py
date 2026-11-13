"""The Prowler invocation contract (scanner-connectors spec, Prowler invocation).

The argv is fixed per provider; only the excluded check ids vary, and each must be a plain check
id so none can pass as a flag. The child process environment is built from scratch: the parent's
environment (task role, AWS settings) never reaches Prowler, and the credential reaches it only
here, never on argv or disk.
"""

import re
from collections.abc import Iterable, Mapping

_PROWLER_PROVIDER = {"m365": "m365", "google_workspace": "googleworkspace"}
_AUTH = {"m365": ["--certificate-auth"], "google_workspace": []}
_CHECK_ID = re.compile(r"[a-z0-9]+(_[a-z0-9]+)+")
# Prowler 5.49.0: certificate auth reads these three (m365_provider.py:437); the Google provider
# reads only GOOGLEWORKSPACE_* (googleworkspace_provider.py:246, :305-359).
_CREDENTIAL = {
    "m365": frozenset({"AZURE_CLIENT_ID", "AZURE_TENANT_ID", "M365_CERTIFICATE_CONTENT"}),
    "google_workspace": frozenset(
        {"GOOGLEWORKSPACE_CREDENTIALS_CONTENT", "GOOGLEWORKSPACE_DELEGATED_USER"}
    ),
}
_BASE_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/home/scanner",  # tmpfs: PowerShell caches on a read-only root filesystem
    "TMPDIR": "/work/tmp",
    "LANG": "C.UTF-8",
    "POWERSHELL_TELEMETRY_OPTOUT": "1",
}


def _provider(provider: str) -> str:
    if provider not in _PROWLER_PROVIDER:
        raise ValueError("unknown provider")
    return provider


def prowler_argv(provider: str, excluded: Iterable[str]) -> list[str]:
    checks = sorted(excluded)
    for check in checks:
        if not _CHECK_ID.fullmatch(check):
            raise ValueError("excluded entry is not a check id")
    argv = [
        "prowler",
        _PROWLER_PROVIDER[_provider(provider)],
        *_AUTH[provider],
        *("-M", "json-ocsf", "-o", "/work/out", "-F", "prowler", "--no-banner"),
        *("--log-level", "ERROR", "--log-file", "/work/prowler.log", "-z"),
    ]
    return [*argv, "--excluded-checks", *checks] if checks else argv


def child_env(provider: str, credential: Mapping[str, str]) -> dict[str, str]:
    """The whole environment of the Prowler process. Errors name variables, never values."""
    expected = _CREDENTIAL[_provider(provider)]
    if set(credential) != expected:
        names = ", ".join(sorted(set(credential) ^ expected))
        raise ValueError(f"credential must hold exactly the {provider} variables: {names}")
    empty = sorted(name for name, value in credential.items() if not value)
    if empty:
        raise ValueError(f"credential variables are empty: {', '.join(empty)}")
    return {**_BASE_ENV, **credential}
