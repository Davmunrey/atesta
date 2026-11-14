"""The verifier's Graph token: client credentials with Atesta's one M365 certificate (D5).

The same azure-identity CertificateCredential Prowler 5.49.0 uses (m365_provider.py:595-601),
which ships in the image with Prowler. Only Entra's answers that mean the customer removed the
app or its consent count as `revoked`; any other refusal is Atesta's own credential problem and
never changes the connection. Errors never carry Entra's message (it can echo the client).
"""

import base64
import binascii

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
# AADSTS700016 app not found in the tenant, AADSTS7000112 app disabled, AADSTS65001 no consent.
_REVOKED = ("AADSTS700016", "AADSTS7000112", "AADSTS65001")


class TokenRevokedError(Exception):
    """The tenant no longer has the scanner app or its consent."""


class TokenUnavailableError(Exception):
    """Atesta's credential was refused or unusable: exit 11, the connection is unchanged."""


class TokenTransientError(Exception):
    """The token endpoint could not be reached."""


def m365_graph_token(client_id: str, tenant: str, certificate_b64: str) -> str:
    from azure.core.exceptions import (  # type: ignore[import-not-found]
        ClientAuthenticationError,
        ServiceRequestError,
    )
    from azure.identity import CertificateCredential  # type: ignore[import-not-found]

    try:
        certificate = base64.b64decode(certificate_b64, validate=True)
    except (binascii.Error, ValueError):
        raise TokenUnavailableError("the certificate is not base64") from None
    if not certificate:
        raise TokenUnavailableError("the certificate is empty")
    try:
        credential = CertificateCredential(
            tenant_id=tenant, client_id=client_id, certificate_data=certificate
        )
        return str(credential.get_token(GRAPH_SCOPE).token)
    except ServiceRequestError:
        raise TokenTransientError("the token endpoint is unreachable") from None
    except ClientAuthenticationError as refused:
        if any(code in str(refused) for code in _REVOKED):
            raise TokenRevokedError("the tenant removed the app or its consent") from None
        raise TokenUnavailableError("the credential was refused") from None
    except ValueError:  # a certificate azure-identity cannot load
        raise TokenUnavailableError("the certificate cannot be loaded") from None
