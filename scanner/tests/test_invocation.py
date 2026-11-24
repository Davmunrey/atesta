"""The Prowler invocation contract (scanner-connectors spec, Prowler invocation)."""

import pytest
from atesta_core.exclusions import D3_CHECKS, D6_CHECKS
from atesta_scanner.invocation import child_env, prowler_argv

COMMON = ["-M", "json-ocsf", "-o", "/work/out", "-F", "prowler", "--no-banner"]
LOGS = ["--log-level", "ERROR", "--log-file", "/work/prowler.log", "-z"]
POWERSHELL = ["teams_meeting_recording_disabled", "exchange_transport_config_smtp_auth_disabled"]
FORBIDDEN = {
    "--push-to-cloud",
    "--fixer",
    "--status",
    "--scan-secrets-validate",
    "--tenant-id",
    "--init-modules",
    "DEBUG",
    "INFO",
}


def test_m365_argv_is_exact() -> None:
    excluded = [*POWERSHELL, *D3_CHECKS]
    assert prowler_argv("m365", excluded) == [
        "prowler",
        "m365",
        "--certificate-auth",
        *COMMON,
        *LOGS,
        "--excluded-checks",
        *sorted(excluded),
    ]


def test_google_argv_is_exact() -> None:
    assert prowler_argv("google_workspace", D6_CHECKS) == [
        "prowler",
        "googleworkspace",
        *COMMON,
        *LOGS,
        "--excluded-checks",
        *sorted(D6_CHECKS),
    ]


@pytest.mark.parametrize("provider", ["m365", "google_workspace"])
def test_no_forbidden_flag_ever_appears(provider: str) -> None:
    assert not FORBIDDEN & set(prowler_argv(provider, ["entra_x_y"]))
    assert "--excluded-checks" not in prowler_argv(provider, [])  # nargs + needs a value


@pytest.mark.parametrize("check", ["--fixer", "entra_x y", "", "../x", "Entra_x"])
def test_an_excluded_check_cannot_smuggle_a_flag(check: str) -> None:
    with pytest.raises(ValueError, match="check id"):
        prowler_argv("m365", [check])


def test_an_unknown_provider_is_refused() -> None:
    with pytest.raises(ValueError, match="provider"):
        prowler_argv("aws", [])


BASE = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/home/scanner",
    "TMPDIR": "/work/tmp",
    "LANG": "C.UTF-8",
    "POWERSHELL_TELEMETRY_OPTOUT": "1",
}
M365_SECRET = {"AZURE_CLIENT_ID": "client", "M365_CERTIFICATE_CONTENT": "cGZ4LXNlY3JldA=="}
TENANT = "abcdef01-1111-4111-8111-111111111111"
GOOGLE_SECRET = {"GOOGLEWORKSPACE_CREDENTIALS_CONTENT": '{"private_key": "k"}'}
SUBJECT = "admin@example.com"


def test_the_child_gets_only_the_listed_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "never-inherited")
    pinned = {**BASE, **M365_SECRET, "AZURE_TENANT_ID": TENANT}  # from the job, never the secret
    assert child_env("m365", M365_SECRET, TENANT) == pinned
    # The subject comes from job.json (issue 390), never from a stored secret.
    delegated = {**BASE, **GOOGLE_SECRET, "GOOGLEWORKSPACE_DELEGATED_USER": SUBJECT}
    assert child_env("google_workspace", GOOGLE_SECRET, "C0abc", SUBJECT) == delegated


def test_a_google_child_needs_the_jobs_subject_and_never_names_it() -> None:
    for subject in (None, ""):
        with pytest.raises(ValueError, match="subject"):
            child_env("google_workspace", GOOGLE_SECRET, "C0abc", subject)


@pytest.mark.parametrize("tenant", ["", "tenant", TENANT.upper(), f"{TENANT}\n"])
def test_the_m365_tenant_pin_must_be_a_tenant_id(tenant: str) -> None:
    with pytest.raises(ValueError, match="tenant pin"):
        child_env("m365", M365_SECRET, tenant)


@pytest.mark.parametrize(
    ("provider", "credential"),
    [
        ("m365", {k: v for k, v in M365_SECRET.items() if k != "M365_CERTIFICATE_CONTENT"}),
        ("m365", {**M365_SECRET, "AZURE_CLIENT_SECRET": "s3cret-value"}),
        ("m365", {**M365_SECRET, "AZURE_TENANT_ID": TENANT}),  # a secret never names a tenant
        ("m365", {**M365_SECRET, "AZURE_CLIENT_ID": ""}),
        ("google_workspace", M365_SECRET),
        # D7: the verifier key never reaches Prowler, and a stored secret never names the subject.
        (
            "google_workspace",
            {**GOOGLE_SECRET, "ATESTA_GOOGLE_VERIFIER_CREDENTIALS_CONTENT": '{"k": "verifier"}'},
        ),
        ("google_workspace", {**GOOGLE_SECRET, "GOOGLEWORKSPACE_DELEGATED_USER": SUBJECT}),
    ],
)
def test_a_credential_must_have_exactly_its_variables(
    provider: str, credential: dict[str, str]
) -> None:
    with pytest.raises(ValueError, match="credential") as error:
        child_env(provider, credential, TENANT, SUBJECT)
    assert not any(v and v in str(error.value) for v in credential.values())  # rule 2
