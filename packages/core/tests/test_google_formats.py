"""Google connection identifiers, validated once for the API and the scanner (issue 398).

The super admin email reaches a users.get path and Prowler's environment; the domain, customer id
and service account ids reach the scanner's job file. Each has one format, defined here.
"""

import pytest
from atesta_core.connectors.google import (
    email_domain,
    is_customer_id,
    is_domain,
    is_service_account_id,
    is_subject_email,
)


@pytest.mark.parametrize(
    "email",
    ["admin@example.es", "Ana.Gil@Example.ES", "o'neil_ti-01@sub.example.com", "a+b@x.io"],
)
def test_a_google_username_at_a_dns_domain_is_a_subject(email: str) -> None:
    assert is_subject_email(email)


@pytest.mark.parametrize(
    "email",
    [
        "",
        "admin",
        "admin@localhost",
        "../admin@example.es",
        "admin@example.es/x",
        "admin@@example.es",
        "admin @example.es",
        "admin@example.es\n",
        "a" * 65 + "@example.es",
        "admin@" + "a" * 250 + ".es",
        "admin@-example.es",
    ],
)
def test_anything_else_is_refused(email: str) -> None:
    assert not is_subject_email(email)


def test_the_domain_of_an_email_is_lowercase() -> None:
    assert email_domain("Ana@Example.ES") == "example.es"


@pytest.mark.parametrize(
    ("value", "domain", "customer"),
    [
        ("example.es", True, False),
        ("sub.example.co.uk", True, False),
        ("Example.es", False, False),  # domains are kept lowercase
        ("example", False, False),
        ("C0fixture1", False, True),
        ("C03az79cb", False, True),
        ("C0 fixture", False, False),
        ("my_customer", False, False),
    ],
)
def test_a_tenant_is_a_lowercase_domain_or_a_customer_id(
    value: str, domain: bool, customer: bool
) -> None:
    assert (is_domain(value), is_customer_id(value)) == (domain, customer)


@pytest.mark.parametrize(
    ("value", "valid"),
    [("111111111111111111111", True), ("123456", True), ("12345", False), ("1a2", False)],
)
def test_a_service_account_id_is_numeric(value: str, valid: bool) -> None:
    assert is_service_account_id(value) is valid
