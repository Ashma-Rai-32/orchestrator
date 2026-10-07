from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine
from taskiq import InMemoryBroker

from staffroom_api.routes import catalog, employees, goals, health, tenants
from staffroom_api.settings import Settings
from staffroom_api.worker import broker


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Shared clients live for the app's lifetime; routes read them from app.state.
        app.state.settings = settings
        app.state.db = create_async_engine(settings.database_url, pool_pre_ping=True)
        app.state.redis = Redis.from_url(settings.redis_url, socket_timeout=2)
        await _start_broker(app, settings)
        yield
        if not isinstance(broker, InMemoryBroker):  # in-memory shares (and would close) our clients
            await broker.shutdown()
        await app.state.redis.aclose()
        await app.state.db.dispose()

    app = FastAPI(title="Staffroom API", lifespan=lifespan)
    for module in (health, catalog, tenants, employees, goals):
        app.include_router(module.router)
    return app


async def _start_broker(app: FastAPI, settings: Settings) -> None:
    if isinstance(broker, InMemoryBroker):
        # Tests: tasks run inline in this process, so share this app's clients.
        broker.state.db, broker.state.redis = app.state.db, app.state.redis
        broker.state.model = settings.staffroom_model
    else:
        await broker.startup()  # client side: only connects, to enqueue


app = create_app()
