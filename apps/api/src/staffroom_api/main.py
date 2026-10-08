from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine
from taskiq import InMemoryBroker

from staffroom_api.auth import TokenVerifier
from staffroom_api.routes import catalog, employees, goals, health, inbox, tenants
from staffroom_api.secrets import OpenBaoSecretStore, SecretStore
from staffroom_api.settings import Settings
from staffroom_api.worker import broker


def create_app(
    settings: Settings | None = None,
    verifier: TokenVerifier | None = None,
    secrets: SecretStore | None = None,
) -> FastAPI:
    settings = settings or Settings()
    verifier = verifier or TokenVerifier.from_settings(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Shared clients live for the app's lifetime; routes read them from app.state.
        app.state.settings = settings
        app.state.verifier = verifier
        app.state.secrets = secrets or _secret_store(settings)
        app.state.db = create_async_engine(settings.database_url, pool_pre_ping=True)
        app.state.redis = Redis.from_url(settings.redis_url, socket_timeout=2)
        await _start_broker(app, settings)
        yield
        if not isinstance(broker, InMemoryBroker):  # in-memory shares (and would close) our clients
            await broker.shutdown()
        await app.state.redis.aclose()
        await app.state.db.dispose()

    app = FastAPI(title="Staffroom API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,  # bearer tokens, no cookies
    )
    for module in (health, catalog, tenants, employees, goals, inbox):
        app.include_router(module.router)
    return app


def _secret_store(settings: Settings) -> SecretStore | None:
    if settings.openbao_token is None:
        return None
    return OpenBaoSecretStore(settings.openbao_url, settings.openbao_token.get_secret_value())


async def _start_broker(app: FastAPI, settings: Settings) -> None:
    if isinstance(broker, InMemoryBroker):
        # Tests: tasks run inline in this process, so share this app's clients.
        broker.state.db, broker.state.redis = app.state.db, app.state.redis
        broker.state.settings = settings
    else:
        await broker.startup()  # client side: only connects, to enqueue


app = create_app()
