"""Table-class registry (ADR-012): every table in exactly one class."""

from atesta_api.platform.tables import APPEND_ONLY, TENANT, duplicated


def test_no_table_is_in_two_classes() -> None:
    assert duplicated() == []


def test_append_only_tables_are_tenant_tables() -> None:
    """The startup guard checks append-only tables by name; they must also get tenant checks."""
    assert APPEND_ONLY <= TENANT
