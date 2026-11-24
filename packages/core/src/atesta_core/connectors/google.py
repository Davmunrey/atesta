"""Google connection identifiers (scanner-connectors spec, Google verifier contract; issue 398).

One definition for the API, which stores them, and the scanner, which places them in a users.get
path, a job file and Prowler's environment. Google usernames are letters, digits, dashes,
underscores, apostrophes and periods; the domain is a DNS name. Pure, no I/O.
"""

import re

_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_EMAIL = re.compile(rf"[A-Za-z0-9._'+-]{{1,64}}@(?:{_LABEL}\.)+[A-Za-z]{{2,63}}")
_DOMAIN = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
_CUSTOMER_ID = re.compile(r"C[0-9A-Za-z]{4,20}")
_SERVICE_ACCOUNT_ID = re.compile(r"[0-9]{6,30}")  # OAuth client id or IAM uniqueId


def is_subject_email(value: str) -> bool:
    """The super admin email Atesta reads as: never a path, a space or a control character."""
    return len(value) <= 254 and _EMAIL.fullmatch(value) is not None


def email_domain(email: str) -> str:
    return email.rsplit("@", 1)[1].lower()


def is_domain(value: str) -> bool:
    """A lowercase DNS domain, as the entered primary domain is stored."""
    return len(value) <= 253 and _DOMAIN.fullmatch(value) is not None


def is_customer_id(value: str) -> bool:
    """A Google Workspace customer id, as `customers.get('my_customer')` returns it."""
    return _CUSTOMER_ID.fullmatch(value) is not None


def is_service_account_id(value: str) -> bool:
    return _SERVICE_ACCOUNT_ID.fullmatch(value) is not None
