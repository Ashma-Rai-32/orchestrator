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
