"""Background worker: Taskiq broker and the run task (ADR-0004).

Start a worker:  taskiq worker staffroom_api.worker:broker
The API only enqueues (`run_segment.kiq(...)`); the work happens here.
"""

import uuid
from functools import partial
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from taskiq import AsyncBroker, Context, InMemoryBroker, TaskiqDepends, TaskiqEvents, TaskiqState

from staffroom_api.agents.checkpoints import run_checkpointer
from staffroom_api.agents.deploy import SiteHost, site_slug
from staffroom_api.agents.models import chat_model
from staffroom_api.agents.team import EmployeeSpec, Publishing, build_team, toolsets_needed
from staffroom_api.agents.toolsets import open_toolsets
from staffroom_api.broker import ReclaimingRedisStreamBroker
from staffroom_api.db.models import Employee, Run, Tenant
from staffroom_api.db.tenancy import tenant_transaction
from staffroom_api.observability import init_tracing, shutdown_tracing
from staffroom_api.runs import execute_run, fail_run
from staffroom_api.sandbox import run_sandbox
from staffroom_api.secrets import OpenBaoSecretStore, load_all
from staffroom_api.settings import Settings

settings = Settings()


def _make_broker(s: Settings) -> AsyncBroker:
    if s.task_broker == "memory":
        return InMemoryBroker(await_inplace=True)  # tests: the task runs inside .kiq()
    return ReclaimingRedisStreamBroker(  # upstream RedisStreamBroker + reclaim fix
        s.redis_url,
        queue_name="staffroom:runs",
        idle_timeout=s.redelivery_after_seconds * 1000,  # dead worker -> re-claimed after this
    )


broker = _make_broker(settings)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _startup(state: TaskiqState) -> None:
    init_tracing(settings)
    state.db = create_async_engine(settings.database_url, pool_pre_ping=True)
    state.redis = Redis.from_url(settings.redis_url, socket_timeout=5)
    state.settings = settings


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _shutdown(state: TaskiqState) -> None:
    shutdown_tracing()
    await state.redis.aclose()
    await state.db.dispose()


@broker.task(task_name="run_segment", timeout=settings.run_segment_timeout_seconds)
async def run_segment(
    tenant_id: str,
    run_id: str,
    answers: dict[str, str] | None = None,
    context: Context = TaskiqDepends(),
) -> None:
    """Execute one segment of a run: until it finishes or pauses for the admin.

    `answers` ({question_id: answer}) resumes a run that was waiting for the admin.
    """
    tid, rid = uuid.UUID(tenant_id), uuid.UUID(run_id)
    db, redis, s = context.state.db, context.state.redis, context.state.settings

    async with tenant_transaction(db, tid) as conn:
        session = AsyncSession(bind=conn)
        run = await session.get(Run, rid)
        if run is None or run.status in ("succeeded", "failed"):
            return  # idempotent: a redelivered message for a finished run does nothing
        tenant = await session.get(Tenant, tid)
        employees = [
            EmployeeSpec(name=e.name, skills=e.skills)
            for e in await session.scalars(select(Employee))
        ]
        goal = run.goal

    # Checkpoints make the run resumable: if this worker dies, the redelivered
    # message lands on another worker, which continues from the last checkpoint.
    try:
        async with (
            run_checkpointer(s, tid) as checkpointer,
            run_sandbox(s, tid, rid, await _tenant_secrets(s, tid)) as sandbox,
            open_toolsets(toolsets_needed(employees), sandbox) as toolsets,
        ):
            team = build_team(
                employees,
                model=partial(chat_model, s.staffroom_model, s.model_requests_per_second),
                fallbacks=lambda: [
                    chat_model(m, s.model_requests_per_second) for m in s.staffroom_fallback_models
                ],
                checkpointer=checkpointer,
                sandbox=sandbox,
                toolsets=toolsets,
                publishing=_publishing(s, tenant.name if tenant else str(tid)),
            )
            await execute_run(db, redis, tid, rid, team, goal, answers)
    except Exception as exc:
        # Setup failed (sandbox, browser, model config...): fail visibly. Found when a
        # misconfigured fallback model left runs stuck in `queued` forever.
        await fail_run(db, redis, tid, rid, exc)


async def _tenant_secrets(settings: Settings, tenant_id: uuid.UUID) -> dict[str, str]:
    """Loaded per segment, so a key the admin just added is available on resume."""
    if settings.openbao_token is None:
        return {}
    store = OpenBaoSecretStore(settings.openbao_url, settings.openbao_token.get_secret_value())
    return await load_all(store, tenant_id)


def _publishing(settings: Settings, tenant_name: str) -> Publishing | None:
    """Approved sites go to <sites_dir>/sites/<tenant>/ (M6.3); off when unconfigured."""
    if settings.sites_dir is None:
        return None
    host = SiteHost(Path(settings.sites_dir), settings.sites_public_url)
    return Publishing(sites=host, slug=site_slug(tenant_name))
