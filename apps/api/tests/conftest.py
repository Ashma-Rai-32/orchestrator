from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from testcontainers.community.postgres import PostgresContainer

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A throwaway Postgres (same major version as compose) for the whole test session."""
    with PostgresContainer(
        "postgres:17-alpine", username="test", password="test", dbname="test", driver="psycopg"
    ) as pg:
        yield pg.get_connection_url()


# --- pytest-alembic fixtures (it defaults to SQLite otherwise) --------------


@pytest.fixture
def alembic_config() -> dict[str, str]:
    return {"file": str(ALEMBIC_INI)}


@pytest.fixture
def alembic_engine(postgres_url: str) -> Iterator[Engine]:
    engine = create_engine(postgres_url)
    yield engine
    engine.dispose()
