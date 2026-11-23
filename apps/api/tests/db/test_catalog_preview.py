"""Preview catalog projection is local, immutable, transactional and never assessable."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, text
from test_catalog_content import catalog_files, read


@pytest.fixture
def owner(superuser: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Connection]:
    monkeypatch.setenv("ATESTA_ENV", "test")
    with superuser.connect() as conn:
        transaction = conn.begin()
        conn.exec_driver_sql("SET LOCAL ROLE atesta_owner")
        try:
            yield conn
        finally:
            transaction.rollback()


def test_preview_import_is_idempotent_and_preserves_rules(
    owner: Connection, tmp_path: Path
) -> None:
    from atesta_api.modules.compliance.catalog_preview import import_preview

    catalog_files(tmp_path)
    catalog = read(tmp_path)
    assert import_preview(owner, catalog) == ["sample"]
    assert import_preview(owner, catalog) == ["sample"]
    assert owner.scalar(text("SELECT count(*) FROM requirements WHERE framework_key='sample'")) == 1
    row = owner.execute(text("SELECT attributes FROM requirements WHERE framework_key='sample'"))
    assert row.scalar_one()["selection_rules"] == [{"level": "LOW", "rule": "R1 or R2"}]
    assert (
        owner.scalar(text("SELECT reviewed_by FROM mappings WHERE framework_key='sample'")) is None
    )


def test_preview_rejects_changed_content_and_rolls_back(owner: Connection, tmp_path: Path) -> None:
    from atesta_api.modules.compliance.catalog_preview import import_preview

    catalog_files(tmp_path)
    original = read(tmp_path)
    import_preview(owner, original)
    changed = read(tmp_path)
    changed.controls["ctl.review"].description_en = "A different guide"
    with pytest.raises(ValueError, match="conflict"), owner.begin_nested():
        import_preview(owner, changed)
    assert (
        owner.scalar(text("SELECT description_en FROM controls WHERE key='ctl.review'"))
        == "Review the evidence."
    )


def test_preview_refuses_production(
    owner: Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atesta_api.modules.compliance.catalog_preview import import_preview

    catalog_files(tmp_path)
    monkeypatch.setenv("ATESTA_ENV", "production")
    with pytest.raises(RuntimeError, match="ATESTA_ENV"):
        import_preview(owner, read(tmp_path))
    assert owner.scalar(text("SELECT count(*) FROM frameworks WHERE key='sample'")) == 0


def test_the_real_catalog_imports_and_reimports_with_signed_content(owner: Connection) -> None:
    """Regression: #337 signed guide content, whose reviewed_on dates live inside requirement
    attributes (JSONB). The import must serialise them and an exact reimport must be a no-op."""
    from atesta_api.modules.compliance.catalog import read_catalog
    from atesta_api.modules.compliance.catalog_preview import import_preview
    from atesta_api.modules.scanning.expected import ENGINE_VERSION, expected_checks

    root = Path(__file__).resolve().parents[4]
    expected = {
        check
        for provider in ("m365", "google_workspace")
        for check in expected_checks(root / "scanner" / "expected", provider)
    }
    catalog = read_catalog(
        root / "catalog", expected_checks=expected, engine_version=ENGINE_VERSION
    )
    imported = import_preview(owner, catalog)
    assert "ens_rd311_2022" in imported
    assert import_preview(owner, catalog) == imported
    signed = owner.scalar(
        text(
            "SELECT attributes->'expected_evidence'->>'reviewed_on' FROM requirements"
            " WHERE framework_key = 'ens_rd311_2022' AND code = 'org.1'"
        )
    )
    assert signed == "2026-11-23"
