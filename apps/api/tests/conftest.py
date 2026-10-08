import os

os.environ["TASK_BROKER"] = "memory"  # before app imports: tasks run inline (ADR-0004)

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text
from testcontainers.community.postgres import PostgresContainer

from staffroom_api.agents import checkpoints
from staffroom_api.main import create_app
from staffroom_api.settings import Settings
from tests.helpers import fake_verifier

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"
APP_ROLE, APP_PASSWORD = "staffroom_app", "app-test"


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    """A throwaway Postgres (same major version as compose) for the whole test session."""
    with PostgresContainer(
        "postgres:17-alpine", username="test", password="test", dbname="test", driver="psycopg"
    ) as pg:
        yield pg


def _url(pg: PostgresContainer, *, driver: str, user: str, password: str, db: str) -> str:
    host, port = pg.get_container_host_ip(), pg.get_exposed_port(5432)
    return f"postgresql+{driver}://{user}:{password}@{host}:{port}/{db}"


# --- pytest-alembic fixtures (it defaults to SQLite otherwise) --------------


@pytest.fixture
def alembic_config() -> dict[str, str]:
    return {"file": str(ALEMBIC_INI)}


@pytest.fixture
def alembic_engine(postgres: PostgresContainer) -> Iterator[Engine]:
    engine = create_engine(postgres.get_connection_url())
    yield engine
    engine.dispose()


# --- A migrated database for tenant-isolation tests -------------------------


@pytest.fixture(scope="session")
def rls_db(postgres: PostgresContainer) -> dict[str, str]:
    """Separate database at head, with the app role able to log in.

    Separate from pytest-alembic's database, which those tests upgrade and downgrade.
    Returns URLs for the owner (sync, bypasses RLS) and the app role (async, RLS applies).
    """
    admin = create_engine(postgres.get_connection_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("CREATE DATABASE rls"))
    admin.dispose()

    owner = dict(user="test", password="test", db="rls")
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", _url(postgres, driver="asyncpg", **owner))
    command.upgrade(cfg, "head")
    asyncio.run(checkpoints.setup(_url(postgres, driver="asyncpg", **owner)))

    owner_url = _url(postgres, driver="psycopg", **owner)
    engine = create_engine(owner_url)
    with engine.begin() as conn:
        # What infra (compose init script / Terraform) does in real environments.
        conn.execute(text(f"ALTER ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}'"))
    engine.dispose()

    return {
        "owner": owner_url,
        "app": _url(postgres, driver="asyncpg", user=APP_ROLE, password=APP_PASSWORD, db="rls"),
    }


@pytest.fixture(scope="session")
def api_settings(postgres: PostgresContainer, rls_db: dict[str, str]) -> Settings:
    """App settings pointing at the migrated test database, as the app role."""
    return Settings(
        postgres_host=postgres.get_container_host_ip(),
        postgres_port=int(postgres.get_exposed_port(5432)),
        postgres_db="rls",
        app_db_user=APP_ROLE,
        app_db_password=SecretStr(APP_PASSWORD),
        # Deterministic, whatever the developer's .env says (e.g. a real local model).
        staffroom_model="fake",
        staffroom_fallback_models=[],
        model_requests_per_second=None,
        sandbox_backend="none",
        langfuse_public_key=None,
        langfuse_secret_key=None,
    )


@pytest.fixture
def client(api_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(api_settings, verifier=fake_verifier())) as c:
        yield c
