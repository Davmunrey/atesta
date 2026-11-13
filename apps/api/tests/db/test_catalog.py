"""Catalog tables: global, read-only at runtime, provenance enforced (control-model spec)."""

import pytest
from atesta_api.platform.tables import CATALOG
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

# Synthetic content only (rule 10).
SEED = """
INSERT INTO frameworks (key, name, version, jurisdiction, source, license_notes, status)
  VALUES ('fw_test', 'Test pack', '1', 'EU', 'https://example.org/fw', 'test', 'draft');
INSERT INTO requirements (framework_key, code, title_es, source)
  VALUES ('fw_test', 'R-1', 'Requisito uno', 'sec. 1');
INSERT INTO controls (key, title_es, title_en, description_es, description_en)
  VALUES ('ctl.test', 'Control', 'Control', 'Descripción', 'Description');
INSERT INTO checks (engine, check_id, engine_version) VALUES ('atesta', 'chk_test', '0.0.0');
INSERT INTO control_checks (control_key, engine, check_id)
  VALUES ('ctl.test', 'atesta', 'chk_test');
INSERT INTO mappings (framework_key, requirement_code, control_key, rationale, source)
  VALUES ('fw_test', 'R-1', 'ctl.test', 'same intent', 'sec. 1');
"""


@pytest.fixture(scope="module", autouse=True)
def seed(superuser: Engine) -> None:
    with superuser.begin() as conn:
        conn.exec_driver_sql(SEED)


def test_catalog_is_readable_without_tenant_context(db_rollback: Session) -> None:
    query = text(
        "SELECT count(*) FROM mappings m JOIN requirements r ON r.code = m.requirement_code"
    )
    assert db_rollback.execute(query).scalar_one() == 1


@pytest.mark.parametrize("table", sorted(CATALOG))
@pytest.mark.parametrize(
    "statement",
    ["DELETE FROM {t}", "UPDATE {t} SET retired_at = now()", "INSERT INTO {t} DEFAULT VALUES"],
)
def test_catalog_is_read_only_for_the_app(db_rollback: Session, table: str, statement: str) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        db_rollback.execute(text(statement.format(t=table)))


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        ("UPDATE mappings SET source = '  '", "ck_mappings_source_filled"),
        ("UPDATE mappings SET rationale = ''", "ck_mappings_rationale_filled"),
        ("UPDATE mappings SET reviewed_by = ' '", "ck_mappings_reviewed_by"),
        ("UPDATE requirements SET source = ''", "ck_requirements_source_filled"),
        ("UPDATE frameworks SET status = 'published'", "ck_frameworks_status"),
        ("UPDATE checks SET engine = 'other'", "ck_checks_engine"),
        ("INSERT INTO mappings VALUES ('fw_test', 'R-404', 'ctl.test', 'r', 's')", "requirements"),
    ],
)
def test_constraints(superuser: Engine, statement: str, constraint: str) -> None:
    with superuser.connect() as conn, pytest.raises(DBAPIError, match=constraint):
        conn.exec_driver_sql(statement)


def test_unsigned_mapping_is_allowed(superuser: Engine) -> None:
    with superuser.connect() as conn:
        assert conn.exec_driver_sql("SELECT reviewed_by FROM mappings").scalar() is None
