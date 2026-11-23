"""Reference links that are themselves credentials (rule 2; issues #256 and #89).

Evidence statements are append-only, so a link stored with a signature or a token in its query
or fragment could never be purged. Every path that copies a link into evidence refuses it: the
web form, the ingestion API, policies and training campaigns, and record_attestation as the last
barrier. A link whose path is the capability ("anyone with the link") cannot be told apart from
a normal link; SECURITY.md lists it as an accepted gap.
"""

from urllib.parse import parse_qsl, urlsplit

# Azure SAS, S3 and GCS signed URLs, OAuth tokens and API keys.
CREDENTIAL_PARAMETERS = frozenset(
    {
        "sig",
        "signature",
        "x-amz-signature",
        "x-amz-credential",
        "x-amz-security-token",
        "x-goog-signature",
        "x-goog-credential",
        "token",
        "access_token",
        "id_token",
        "refresh_token",
        "code",
        "key",
        "apikey",
        "api_key",
        "password",
        "secret",
    }
)


class CredentialLinkError(ValueError):
    """The link carries a credential and must never be stored."""


def carries_credential(url: str) -> bool:
    parts = urlsplit(url)
    names = {
        name.lower()
        for part in (parts.query, parts.fragment)
        for name, _ in parse_qsl(part, keep_blank_values=True)
    }
    return bool(names & CREDENTIAL_PARAMETERS)


def refuse_credential_link(url: str) -> str:
    """For input validators: the link unchanged, or a ValueError that becomes a 422."""
    if carries_credential(url):
        raise CredentialLinkError(
            "the link carries a signature or a token; share one that asks to sign in"
        )
    return url
