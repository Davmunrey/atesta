"""Google read-only verification (scanner-connectors spec, Google verifier contract).

Recorded Admin SDK answers stand in for a Workspace tenant. Fail closed: anything extra is
over_privileged, anything missing incomplete, a removal revoked, and nothing unreadable is ever
`ok`. The verifier key only reads the audit log; the scan key reads everything else (D7).
"""

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from atesta_core.connectors.readonly import GOOGLE_V1
from atesta_scanner.entra_token import TokenTransientError, TokenUnavailableError
from atesta_scanner.google_api import GoogleDeniedError, GoogleTransientError
from atesta_scanner.google_token import ServiceAccountKey, TokenRefusedError, load_key
from atesta_scanner.verify_google import (
    AUTHORIZE,
    GOOGLE_LIMITS,
    REMOVE,
    REPORTS,
    GoogleTarget,
    verify_google,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

DIRECTORY = "admin/directory/v1/"
CUSTOMER = "C0fixture1"
SUBJECT = "admin@example.es"
SCAN_ID, VERIFIER_ID = "111111111111111111111", "222222222222222222222"  # OAuth client ids
SCAN_UID, VERIFIER_UID = "333333333333333333333", "444444444444444444444"  # IAM uniqueIds
GRANTED_AT = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
LICENSING = "https://www.googleapis.com/auth/apps.licensing"
PEM = (
    rsa.generate_private_key(public_exponent=65537, key_size=2048)
    .private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    .decode()
)


def key(client_id: str) -> ServiceAccountKey:
    return load_key(
        json.dumps(
            {
                "type": "service_account",
                "private_key_id": "ab" * 20,
                "private_key": PEM,
                "client_email": f"sa-{client_id}@atesta-dev.iam.gserviceaccount.com",
                "client_id": client_id,
            }
        )
    )


SCAN_KEY, VERIFIER_KEY = key(SCAN_ID), key(VERIFIER_ID)


def activity(name: str, client: str, at: datetime, scopes: Any = None) -> dict[str, Any]:
    parameters: list[dict[str, Any]] = [{"name": "API_CLIENT_NAME", "value": client}]
    if scopes is not None:
        parameters.append(
            {
                "name": "API_SCOPES",
                **(
                    {"value": scopes} if isinstance(scopes, str) else {"multiValue": sorted(scopes)}
                ),
            }
        )
    parameters.append({"name": "DOMAIN_NAME", "value": "example.es"})
    return {
        "id": {"time": at.isoformat().replace("+00:00", "Z"), "applicationName": "admin"},
        "events": [{"type": "DOMAIN_SETTINGS", "name": name, "parameters": parameters}],
    }


def granted(client: str, scopes: Any, at: datetime = GRANTED_AT) -> dict[str, Any]:
    return activity(AUTHORIZE, client, at, scopes)


def removed(client: str, at: datetime) -> dict[str, Any]:
    return activity(REMOVE, client, at)


class FakeGoogle:
    """Answers like a recorded Workspace tenant and records which token read what."""

    def __init__(self) -> None:
        self.answers: dict[str, Any] = {
            DIRECTORY + "customers/my_customer": {"id": CUSTOMER, "customerDomain": "example.es"},
            DIRECTORY + "customer/my_customer/domains": {
                "domains": [
                    {
                        "domainName": "example.es",
                        "verified": True,
                        "isPrimary": True,
                        "domainAliases": [{"domainAliasName": "alias.es", "verified": True}],
                    },
                    {"domainName": "second.es", "verified": True, "isPrimary": False},
                    {"domainName": "pending.es", "verified": False, "isPrimary": False},
                ]
            },
            DIRECTORY + f"users/{SUBJECT}": {"isAdmin": True, "suspended": False},
            DIRECTORY + "customer/my_customer/roleassignments": [
                {"roleAssignmentId": "91", "roleId": "7", "assignedTo": "555555555555555555555"}
            ],
        }
        self.events: dict[str, list[dict[str, Any]]] = {
            AUTHORIZE: [
                granted(SCAN_ID, GOOGLE_V1.scan_scopes),
                granted(VERIFIER_ID, GOOGLE_V1.verifier_scopes),
                granted("999999999999999999999", {LICENSING}),  # another org's client
            ],
            REMOVE: [],
        }
        self.refusals: dict[str, Exception] = {}  # client id -> what minting raises
        self.minted: list[tuple[str, frozenset[str]]] = []
        self.reads: list[tuple[str, str, Mapping[str, str] | None]] = []

    def mint(self, sa: ServiceAccountKey, scopes: frozenset[str]) -> str:
        self.minted.append((sa.client_id, scopes))
        if sa.client_id in self.refusals:
            raise self.refusals[sa.client_id]
        return f"tok-{sa.client_id}"

    def read(self, token: str) -> "Reader":
        return Reader(self, token)

    def paths(self, token: str) -> set[str]:
        return {path for t, path, _ in self.reads if t == token}


class Reader:
    def __init__(self, fake: FakeGoogle, token: str) -> None:
        self.fake, self.token = fake, token

    def _answer(self, path: str, params: Mapping[str, str] | None) -> Any:
        self.fake.reads.append((self.token, path, params))
        answer = self.fake.answers[path]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def get(self, path: str, params: Mapping[str, str] | None = None) -> Any:
        return self._answer(path, params)

    def get_all(
        self, path: str, items_key: str, params: Mapping[str, str] | None = None
    ) -> list[Any]:
        if path != REPORTS:
            return list(self._answer(path, params))
        self.fake.reads.append((self.token, path, params))
        assert params is not None
        start = params.get("startTime")
        return [
            event
            for event in self.fake.events[params["eventName"]]
            if start is None or event["id"]["time"] >= start
        ]


def target(**changes: Any) -> GoogleTarget:
    base: dict[str, Any] = {
        "subject": SUBJECT,
        "tenant": CUSTOMER,
        "unique_ids": (SCAN_UID, VERIFIER_UID),
        "since": None,
        "version": "google-v1",
    }
    return GoogleTarget(**{**base, **changes})


def verify(fake: FakeGoogle, full: bool = True, **changes: Any) -> dict[str, Any]:
    return verify_google(
        fake.mint, fake.read, target(**changes), SCAN_KEY, VERIFIER_KEY if full else None
    )


def test_exactly_the_allowlist_is_ok_and_each_key_reads_only_its_own_apis() -> None:
    fake = FakeGoogle()
    report = verify(fake)
    assert report["verdict"] == "ok"
    assert (report["tenant_id"], report["missing"], report["extra"]) == (CUSTOMER, [], [])
    assert report["granted"] == {
        "scan_scopes": sorted(GOOGLE_V1.scan_scopes),
        "verifier_scopes": sorted(GOOGLE_V1.verifier_scopes),
        "role_assignments": [],
    }
    assert report["limits"] == list(GOOGLE_LIMITS)
    # Step 1: each key asks for exactly its client's scopes.
    assert fake.minted == [
        (VERIFIER_ID, GOOGLE_V1.verifier_scopes),
        (SCAN_ID, GOOGLE_V1.scan_scopes),
    ]
    # D7: the verifier token reads the audit log and nothing else.
    assert fake.paths(f"tok-{VERIFIER_ID}") == {REPORTS}
    assert REPORTS not in fake.paths(f"tok-{SCAN_ID}")
    assert SUBJECT not in json.dumps(report)  # ids, scopes and verdicts only


def test_a_scan_run_rechecks_token_and_identity_with_the_scan_key_only() -> None:
    fake = FakeGoogle()
    report = verify(fake, full=False)
    assert report["verdict"] == "ok" and report["tenant_id"] == CUSTOMER
    assert fake.minted == [(SCAN_ID, GOOGLE_V1.scan_scopes)]
    assert fake.paths(f"tok-{SCAN_ID}") == {
        DIRECTORY + "customers/my_customer",
        DIRECTORY + "customer/my_customer/domains",
        DIRECTORY + f"users/{SUBJECT}",
    }


def test_an_extra_scope_on_either_client_is_over_privileged() -> None:
    for client, expected in ((SCAN_ID, GOOGLE_V1.scan_scopes), (VERIFIER_ID, set())):
        fake = FakeGoogle()
        fake.events[AUTHORIZE].append(
            granted(client, {*expected, LICENSING}, GRANTED_AT + timedelta(hours=1))
        )
        report = verify(fake)
        assert report["verdict"] == "over_privileged"
        label = "scan" if client == SCAN_ID else "verifier"
        assert f"{label} {LICENSING}" in report["extra"]


def test_a_missing_scope_is_incomplete() -> None:
    fake = FakeGoogle()
    fewer = sorted(GOOGLE_V1.scan_scopes)[1:]
    fake.events[AUTHORIZE].append(granted(SCAN_ID, fewer, GRANTED_AT + timedelta(hours=1)))
    report = verify(fake)
    assert report["verdict"] == "incomplete"
    assert report["missing"] == [f"scan {sorted(GOOGLE_V1.scan_scopes)[0]}"]


def test_scopes_may_arrive_as_one_comma_separated_value() -> None:
    fake = FakeGoogle()
    fake.events[AUTHORIZE][0] = granted(SCAN_ID, ", ".join(sorted(GOOGLE_V1.scan_scopes)))
    assert verify(fake)["verdict"] == "ok"


@pytest.mark.parametrize("assignee", [SCAN_UID, VERIFIER_UID, SCAN_ID, VERIFIER_ID])
def test_any_admin_role_on_either_service_account_is_over_privileged(assignee: str) -> None:
    fake = FakeGoogle()
    fake.answers[DIRECTORY + "customer/my_customer/roleassignments"].append(
        {"roleAssignmentId": "92", "roleId": "8", "assignedTo": assignee}
    )
    report = verify(fake)
    assert report["verdict"] == "over_privileged"
    assert report["granted"]["role_assignments"] == ["92"]
    assert report["extra"] == ["1 admin role assignment(s)"]
    assert fake.paths(f"tok-{SCAN_ID}") >= {DIRECTORY + "customer/my_customer/roleassignments"}


def test_a_removal_after_the_last_grant_is_revoked_and_a_new_grant_restores_it() -> None:
    fake = FakeGoogle()
    fake.events[REMOVE].append(removed(SCAN_ID, GRANTED_AT + timedelta(days=1)))
    assert verify(fake)["verdict"] == "revoked"
    fake.events[AUTHORIZE].append(
        granted(SCAN_ID, GOOGLE_V1.scan_scopes, GRANTED_AT + timedelta(days=2))
    )
    assert verify(fake)["verdict"] == "ok"


def test_a_grant_and_a_removal_at_the_same_instant_is_revoked() -> None:
    fake = FakeGoogle()
    fake.events[REMOVE].append(removed(VERIFIER_ID, GRANTED_AT))
    assert verify(fake)["verdict"] == "revoked"


def test_a_removed_scan_client_is_revoked_even_though_its_token_is_refused() -> None:
    fake = FakeGoogle()
    fake.refusals[SCAN_ID] = TokenRefusedError("not_authorized")
    fake.events[REMOVE].append(removed(SCAN_ID, GRANTED_AT + timedelta(days=1)))
    assert verify(fake)["verdict"] == "revoked"


@pytest.mark.parametrize(
    ("client", "reason", "missing"),
    [
        (SCAN_ID, "not_authorized", "scan_client_not_authorized"),
        (VERIFIER_ID, "not_authorized", "verifier_client_not_authorized"),
        (SCAN_ID, "blocked_by_policy", "scan_client_blocked_by_policy"),
        (VERIFIER_ID, "delegated_user", "delegated_user"),
    ],
)
def test_a_refused_token_is_incomplete_and_names_what_to_fix(
    client: str, reason: str, missing: str
) -> None:
    fake = FakeGoogle()
    fake.refusals[client] = TokenRefusedError(reason)
    report = verify(fake)
    assert (report["verdict"], report["missing"]) == ("incomplete", [missing])


def test_token_outages_are_transient_and_atestas_own_refusals_are_raised() -> None:
    fake = FakeGoogle()
    fake.refusals[SCAN_ID] = TokenTransientError("down")
    assert verify(fake)["verdict"] == "transient"
    fake.refusals[SCAN_ID] = TokenUnavailableError("refused")
    with pytest.raises(TokenUnavailableError):  # exit 11: the connection is unchanged
        verify(fake)


def test_the_pinned_customer_must_be_the_one_read() -> None:
    fake = FakeGoogle()
    report = verify(fake, tenant="C0another1")
    assert (report["verdict"], report["missing"]) == ("incomplete", ["customer_pin"])
    assert report["tenant_id"] == CUSTOMER


def test_before_the_pin_the_entered_domain_must_be_the_verified_primary_domain() -> None:
    fake = FakeGoogle()
    report = verify(fake, tenant="example.es")
    assert (report["verdict"], report["tenant_id"]) == ("ok", CUSTOMER)  # what the API pins
    for domain in ("second.es", "alias.es", "pending.es", "elsewhere.es"):
        report = verify(FakeGoogle(), tenant=domain)
        assert (report["verdict"], report["missing"]) == ("incomplete", ["primary_domain"])


@pytest.mark.parametrize(
    ("subject", "user", "missing"),
    [
        ("admin@alias.es", {"isAdmin": True, "suspended": False}, []),
        ("admin@second.es", {"isAdmin": True, "suspended": False}, []),
        ("admin@pending.es", {"isAdmin": True, "suspended": False}, ["delegated_user_domain"]),
        ("admin@other.es", {"isAdmin": True, "suspended": False}, ["delegated_user_domain"]),
        (SUBJECT, {"isAdmin": False, "isDelegatedAdmin": True}, ["delegated_user_not_super_admin"]),
        (SUBJECT, {"suspended": False}, ["delegated_user_not_super_admin"]),
        (SUBJECT, {"isAdmin": True, "suspended": True}, ["delegated_user_suspended"]),
        (SUBJECT, GoogleDeniedError("gone", 404), ["delegated_user"]),
    ],
)
def test_the_subject_is_a_super_admin_of_one_of_the_customers_domains(
    subject: str, user: Any, missing: list[str]
) -> None:
    fake = FakeGoogle()
    fake.answers[DIRECTORY + f"users/{subject}"] = user
    report = verify(fake, subject=subject)
    assert report["missing"] == missing
    assert report["verdict"] == ("incomplete" if missing else "ok")


def test_re_reads_start_one_hour_before_the_last_verification() -> None:
    fake = FakeGoogle()
    since = GRANTED_AT + timedelta(days=30)
    report = verify(fake, since=since)  # no event since: nothing changed after the last `ok`
    assert report["verdict"] == "ok"
    assert report["granted"]["scan_scopes"] == sorted(GOOGLE_V1.scan_scopes)
    starts = {p["startTime"] for t, path, p in fake.reads if path == REPORTS and p}
    assert starts == {"2026-12-20T08:00:00.000Z"}
    fake.events[AUTHORIZE].append(
        granted(SCAN_ID, {*GOOGLE_V1.scan_scopes, LICENSING}, since - timedelta(minutes=30))
    )
    assert verify(fake, since=since)["verdict"] == "over_privileged"  # within the overlap


def test_at_activation_a_client_without_an_authorization_event_is_incomplete() -> None:
    fake = FakeGoogle()
    fake.events[AUTHORIZE] = fake.events[AUTHORIZE][1:]  # the scan client's event lags
    report = verify(fake)
    assert (report["verdict"], report["missing"]) == (
        "incomplete",
        ["scan_client_authorization_event"],
    )


def test_reads_it_may_not_make_are_incomplete_and_outages_transient() -> None:
    fake = FakeGoogle()
    fake.answers[DIRECTORY + "customers/my_customer"] = GoogleDeniedError("no", 403)
    report = verify(fake)
    assert (report["verdict"], report["missing"]) == (
        "incomplete",
        ["read access for verification"],
    )
    fake.answers[DIRECTORY + "customers/my_customer"] = GoogleTransientError("429")
    assert verify(fake)["verdict"] == "transient"


@pytest.mark.parametrize(
    "broken",
    [
        {"id": {"time": "yesterday"}, "events": []},
        {"id": {"time": "2026-11-20T09:00:00"}, "events": []},  # no zone
        {"events": []},
        {"id": {"time": "2026-11-20T09:00:00Z"}, "events": [{"name": AUTHORIZE}]},
    ],
)
def test_a_malformed_audit_answer_is_transient_never_ok(broken: dict[str, Any]) -> None:
    fake = FakeGoogle()
    fake.events[AUTHORIZE].append(broken)
    assert verify(fake)["verdict"] == "transient"


def test_an_authorization_without_its_scopes_is_transient_never_ok() -> None:
    fake = FakeGoogle()
    fake.events[AUTHORIZE].append(activity(AUTHORIZE, SCAN_ID, GRANTED_AT + timedelta(hours=1)))
    assert verify(fake)["verdict"] == "transient"
