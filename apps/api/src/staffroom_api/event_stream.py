"""Live fan-out of run events through Redis Streams.

Postgres `events` is the durable record; a Redis stream per run is the live
feed. Streams keep history, so a late subscriber replays from the start
(`XREAD` from id 0) and then continues live, with no gap between the two.
"""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import TimeoutError as RedisTimeoutError

from staffroom_api.agents.events import TeamEvent

TERMINAL = {"run_finished", "run_failed"}
KEEP_AFTER_FINISH_SECONDS = 24 * 3600
_FIELD = "event"
# [(stream key, [(entry id, {field: value})])], all bytes without decode_responses
XReadResult = list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]


def stream_key(tenant_id: uuid.UUID, run_id: uuid.UUID) -> str:
    # Tenant in the key: defence in depth on top of the RLS check before subscribing.
    return f"tenant:{tenant_id}:run:{run_id}:events"


async def publish(
    redis: Redis, tenant_id: uuid.UUID, run_id: uuid.UUID, event_id: int, event: TeamEvent
) -> None:
    key = stream_key(tenant_id, run_id)
    payload = {"id": event_id, "event": event.model_dump()}
    await redis.xadd(key, {_FIELD: json.dumps(payload)}, maxlen=10_000, approximate=True)
    if event.type in TERMINAL:
        await redis.expire(key, KEEP_AFTER_FINISH_SECONDS)


async def exists(redis: Redis, tenant_id: uuid.UUID, run_id: uuid.UUID) -> bool:
    return bool(await redis.exists(stream_key(tenant_id, run_id)))


async def follow(
    redis: Redis, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> AsyncIterator[dict[str, Any]]:
    """Yield every event of the run from the beginning, then live, until it ends."""
    key, last_id = stream_key(tenant_id, run_id), b"0-0"
    while True:
        # Short blocks: the shared client has a 2 s socket timeout. Real models leave long
        # gaps between events, and a busy host can push a read past that timeout: for a
        # poll, a timeout just means "nothing new yet", so poll again.
        try:
            batches = cast(
                XReadResult, await redis.xread({key: last_id}, block=1000, count=100)
            )  # redis-py types this loosely
        except RedisTimeoutError:
            continue
        for _key, entries in batches:
            for entry_id, fields in entries:
                last_id = entry_id
                payload: dict[str, Any] = json.loads(fields[_FIELD.encode()])
                yield payload
                if payload["event"]["type"] in TERMINAL:
                    return
