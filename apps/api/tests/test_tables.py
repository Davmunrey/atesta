"""Table-class registry (ADR-012): every table in exactly one class."""

from atesta_api.platform.tables import (
    APPEND_ONLY,
    GLOBAL_IDENTITY,
    OPERATOR,
    OPERATOR_APPEND_ONLY,
    OPERATOR_READ,
    RETENTION_DAYS,
    TENANT,
    TENANT_ROOT,
    duplicated,
    table_classes,
)


def test_no_table_is_in_two_classes() -> None:
    assert duplicated() == []


def test_append_only_tables_are_tenant_tables() -> None:
    """The startup guard checks append-only tables by name; they must also get tenant checks."""
    assert APPEND_ONLY <= TENANT


def test_retention_tables_are_tenant_tables_and_not_append_only() -> None:
    """A retention table loses rows by age (ADR-012 amendment 9), so it is not append-only."""
    assert set(RETENTION_DAYS) <= TENANT
    assert not set(RETENTION_DAYS) & APPEND_ONLY
    assert all(days >= 1 for days in RETENTION_DAYS.values())


def test_the_operator_column_list_names_classified_metadata_tables_only() -> None:
    """ADR-012 amendment 8: tenant tables, the root and erasure receipts; never users."""
    assert set(OPERATOR_READ) <= set(table_classes())
    assert set(OPERATOR_READ) <= TENANT | {TENANT_ROOT} | OPERATOR
    assert not set(OPERATOR_READ) & GLOBAL_IDENTITY
    assert all(OPERATOR_READ.values())


def test_operator_append_only_tables_are_operator_tables() -> None:
    assert OPERATOR_APPEND_ONLY <= OPERATOR
