"""The verifier's Graph token (scanner-connectors spec, Read-only verification step 1).

azure-identity ships only in the image (with Prowler), so stand-in modules play Entra here.
Only answers that mean the customer removed the app or its consent may revoke a connection; a
network failure is transient and any other refusal is Atesta's credential problem (exit 11).
"""

import base64
import sys
import types
from typing import Any

import pytest
from atesta_scanner.entra_token import (
    GRAPH_SCOPE,
    TokenRevokedError,
    TokenTransientError,
    TokenUnavailableError,
    m365_graph_token,
)

CERT = base64.b64encode(b"pkcs12-bytes").decode()
TENANT = "abcdef01-1111-4111-8111-111111111111"


class ClientAuthenticationError(Exception):
    pass


class ServiceRequestError(Exception):
    pass


def entra(monkeypatch: pytest.MonkeyPatch, outcome: Exception | None) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class CertificateCredential:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(kwargs)

        def get_token(self, scope: str) -> Any:
            calls.append({"scope": scope})
            if outcome is not None:
                raise outcome
            return types.SimpleNamespace(token="graph-token")

    identity = types.ModuleType("azure.identity")
    identity.CertificateCredential = CertificateCredential  # type: ignore[attr-defined]
    exceptions = types.ModuleType("azure.core.exceptions")
    exceptions.ClientAuthenticationError = ClientAuthenticationError  # type: ignore[attr-defined]
    exceptions.ServiceRequestError = ServiceRequestError  # type: ignore[attr-defined]
    for name, module in {
        "azure": types.ModuleType("azure"),
        "azure.core": types.ModuleType("azure.core"),
        "azure.identity": identity,
        "azure.core.exceptions": exceptions,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return calls


def test_the_token_is_for_graph_in_the_pinned_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = entra(monkeypatch, None)
    assert m365_graph_token("client", TENANT, CERT) == "graph-token"
    assert calls == [
        {"tenant_id": TENANT, "client_id": "client", "certificate_data": b"pkcs12-bytes"},
        {"scope": GRAPH_SCOPE},
    ]


@pytest.mark.parametrize("code", ["AADSTS700016", "AADSTS7000112", "AADSTS65001"])
def test_only_a_removed_app_or_consent_revokes(monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    entra(monkeypatch, ClientAuthenticationError(f"{code}: Application not found"))
    with pytest.raises(TokenRevokedError) as error:
        m365_graph_token("client", TENANT, CERT)
    assert code not in str(error.value)  # Entra's message is never carried


def test_any_other_refusal_is_atestas_credential_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    entra(monkeypatch, ClientAuthenticationError("AADSTS700027: certificate expired"))
    with pytest.raises(TokenUnavailableError):
        m365_graph_token("client", TENANT, CERT)


def test_an_unreachable_endpoint_is_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    entra(monkeypatch, ServiceRequestError("connection reset"))
    with pytest.raises(TokenTransientError):
        m365_graph_token("client", TENANT, CERT)


@pytest.mark.parametrize("certificate", ["not base64!", ""])
def test_a_certificate_that_is_not_base64_never_reaches_entra(
    monkeypatch: pytest.MonkeyPatch, certificate: str
) -> None:
    calls = entra(monkeypatch, None)
    with pytest.raises(TokenUnavailableError):
        m365_graph_token("client", TENANT, certificate)
    assert calls == []
