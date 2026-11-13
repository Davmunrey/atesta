"""The Prowler log never carries a secret (scanner-connectors spec, Logs and personal data)."""

import base64

import pytest
from atesta_scanner.scrub import REDACTED, scrub

PFX = base64.b64encode(b"\x30\x82\x0a\x1f-not-a-real-certificate-" * 8).decode()
JWT = (
    "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJhdWQiOiJodHRwczovL2dyYXBoLm1pY3Jvc29mdC5jb20ifQ."
    "c2lnbmF0dXJlLW5vdC1yZWFs"
)
RUN = "QUJD" * 75  # 300 base64 characters
PEM = (
    "-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\\nBKcwggSjAgEAAoIBAQC7\\n"
    "-----END PRIVATE KEY-----\\n"
)


def test_a_forged_prowler_log_comes_out_without_secrets() -> None:
    log = "\n".join(
        [
            "2026-11-13 ERROR m365_powershell.py:212 PowerShell error:",
            f'$cert = [Convert]::FromBase64String("{PFX}")',
            f"token acquired: {JWT}",
            f"blob={RUN}",
            f'{{"private_key": "{PEM}", "client_email": "scanner@example.iam"}}',
            "2026-11-13 ERROR exchange_service.py:88 Get-TransportRule failed",
        ]
    )
    clean = scrub(log, secrets=[PFX])
    for secret in (PFX, JWT, RUN, "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC"):
        assert secret not in clean
    assert clean.count(REDACTED) == 4
    assert "Get-TransportRule failed" in clean  # support context survives


def test_a_secret_is_removed_in_its_base64_forms_too() -> None:
    secret = "s3cret~~~value???entropy"  # its base64 holds "+" and "/"
    standard = base64.b64encode(secret.encode()).decode()
    urlsafe = base64.urlsafe_b64encode(secret.encode()).decode().rstrip("=")
    clean = scrub(f"a {secret} b {standard} c {urlsafe} d", secrets=[secret])
    assert "+" in standard and "/" in standard and "-" in urlsafe and "_" in urlsafe
    assert clean == f"a {REDACTED} b {REDACTED} c {REDACTED} d"


def test_a_multiline_private_key_is_removed() -> None:
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\nqhkiG9w0BAQ\n"
        "-----END RSA PRIVATE KEY-----"
    )
    assert scrub(f"key:\n{pem}\ndone", secrets=[]) == f"key:\n{REDACTED}\ndone"


def test_short_or_empty_secrets_do_not_erase_the_log() -> None:
    # A one-character "secret" would redact every occurrence of that character.
    assert scrub("tenant t ok", secrets=["", "t"]) == "tenant t ok"


@pytest.mark.parametrize(
    "line",
    [
        "2026-11-13 ERROR entra_service.py:64 Graph request failed: 403 (check id entra_x_y)",
        "sha256 e5ed983eb3faf34a72cb0f1460e98516dd5f36ce4db443f886e0d60a205be705 verified",
        "resource /subscriptions/11111111-1111-4111-8111-111111111111/policies/default",
    ],
)
def test_ordinary_lines_are_kept(line: str) -> None:
    assert scrub(line, secrets=[PFX]) == line
