"""One-off database bootstrap (hosted-environment spec): passwords come from the role URLs."""

import pytest
from atesta_api.platform import db_bootstrap

APP = "postgresql+psycopg://atesta_app:app%27s%25pw@db.example:5432/atesta"
OWNER = "postgresql+psycopg://atesta_owner:owner-pw@db.example:5432/atesta"
OPERATOR = "postgresql+psycopg://atesta_operator:operator-pw@db.example:5432/atesta"
ENV = {
    "ATESTA_DATABASE_URL": APP,
    "ATESTA_MIGRATION_DATABASE_URL": OWNER,
    "ATESTA_OPERATOR_DATABASE_URL": OPERATOR,
    "ATESTA_MASTER_PASSWORD": "master-pw",
}


def test_each_role_takes_the_password_from_its_own_url() -> None:
    assert db_bootstrap.role_passwords(ENV) == {
        "atesta_owner": "owner-pw",
        "atesta_app": "app's%pw",
        "atesta_operator": "operator-pw",  # build step 6: the operator service's own login
    }


@pytest.mark.parametrize(
    ("var", "url"),
    [
        ("ATESTA_DATABASE_URL", OWNER),  # wrong role
        ("ATESTA_DATABASE_URL", "postgresql+psycopg://atesta_app@db.example/atesta"),  # no password
        ("ATESTA_OPERATOR_DATABASE_URL", APP),  # the operator never logs in as the app role
        ("ATESTA_OPERATOR_DATABASE_URL", OWNER),
    ],
)
def test_a_url_for_the_wrong_role_or_without_password_is_refused(var: str, url: str) -> None:
    with pytest.raises(ValueError, match=var):
        db_bootstrap.role_passwords({**ENV, var: url})


def test_the_master_connects_to_the_same_host_and_database_as_the_app() -> None:
    master = db_bootstrap.master_url(ENV)
    assert (master.host, master.database, master.port) == ("db.example", "atesta", 5432)
    assert (master.username, master.password) == ("atesta_master", "master-pw")


def test_errors_never_carry_a_password() -> None:
    with pytest.raises(ValueError) as caught:
        db_bootstrap.role_passwords({**ENV, "ATESTA_DATABASE_URL": OWNER})
    assert "owner-pw" not in str(caught.value) and "app's" not in str(caught.value)


def test_the_operator_url_is_required() -> None:
    env = {k: v for k, v in ENV.items() if k != "ATESTA_OPERATOR_DATABASE_URL"}
    with pytest.raises(KeyError, match="ATESTA_OPERATOR_DATABASE_URL"):
        db_bootstrap.role_passwords(env)
