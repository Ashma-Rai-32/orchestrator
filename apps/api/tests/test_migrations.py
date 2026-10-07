"""Standard migration checks, provided by pytest-alembic, run against real Postgres.

- single head: no forked migration history
- upgrade: every migration applies from empty to head
- model/DDL match: models and migrations agree (no forgotten autogenerate)
- up/down consistency: every migration can be downgraded
"""

from pytest_alembic.tests import (  # noqa: F401  (re-exported so pytest collects them)
    test_model_definitions_match_ddl,
    test_single_head_revision,
    test_up_down_consistency,
    test_upgrade,
)
from sqlalchemy import Index, MetaData, Table

from staffroom_api.db.migration_filters import include_object


def test_autogenerate_never_touches_the_checkpointer_tables() -> None:
    """Live finding: autogenerate proposed dropping LangGraph's tables (all run state)."""
    md = MetaData()
    checkpoints = Table("checkpoints", md)
    assert include_object(checkpoints, "checkpoints", "table", True, None) is False
    assert include_object(Index("ix", _table=checkpoints), "ix", "index", True, None) is False
    assert include_object(Table("runs", md), "runs", "table", False, None) is True
