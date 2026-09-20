from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.database import Base, engine


def _table_names() -> set[str]:
    return set(inspect(engine).get_table_names())


def test_migration_downgrade_then_upgrade_roundtrip(alembic_cfg):
    try:
        command.downgrade(alembic_cfg, "base")
        assert "jobs" not in _table_names()
        assert "cameras" not in _table_names()
    finally:
        command.upgrade(alembic_cfg, "head")
    assert "jobs" in _table_names()
    assert "cameras" in _table_names()


def test_models_match_migrations_with_no_drift():
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
