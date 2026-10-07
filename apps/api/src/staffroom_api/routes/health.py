import asyncio
from collections.abc import Awaitable
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text

router = APIRouter()

CheckResult = Literal["ok", "error"]


class Health(BaseModel):
    status: CheckResult
    checks: dict[str, CheckResult]


async def _check(probe: Awaitable[object]) -> CheckResult:
    try:
        await asyncio.wait_for(probe, timeout=2)
    except Exception:
        return "error"
    return "ok"


async def _postgres(request: Request) -> None:
    async with request.app.state.db.connect() as conn:
        await conn.execute(text("SELECT 1"))


@router.get("/health", response_model=Health)
async def health(request: Request, response: Response) -> Health:
    checks: dict[str, CheckResult] = {
        "postgres": await _check(_postgres(request)),
        "redis": await _check(request.app.state.redis.ping()),
    }
    ok = all(v == "ok" for v in checks.values())
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Health(status="ok" if ok else "error", checks=checks)
