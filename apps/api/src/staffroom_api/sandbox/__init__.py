"""Which sandbox backend a run gets (ADR-0006). Everything returned is a deepagents backend."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from deepagents.backends.protocol import SandboxBackendProtocol

from staffroom_api.settings import Settings


@asynccontextmanager
async def run_sandbox(
    settings: Settings, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> AsyncIterator[SandboxBackendProtocol | None]:
    """The run's sandbox, or None when sandboxing is off (tools are then not offered).

    The container is removed when the segment ends; the workspace volume stays, so a
    resumed run (or a later deploy step) finds the files again.
    """
    if settings.sandbox_backend == "none":
        yield None
        return
    if settings.sandbox_backend == "e2b":
        raise NotImplementedError("E2B backend arrives in the next increment (ADR-0006)")

    from staffroom_api.sandbox.docker_backend import DockerSandbox  # docker SDK only if used

    sandbox = await asyncio.to_thread(
        DockerSandbox,
        tenant_id,
        run_id,
        image=settings.sandbox_image,
        runtime=settings.sandbox_runtime,
    )
    try:
        yield sandbox
    finally:
        await asyncio.to_thread(sandbox.close)
