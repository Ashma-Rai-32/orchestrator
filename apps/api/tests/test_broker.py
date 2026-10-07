"""Reclaiming a dead worker's message on an idle queue (taskiq-redis workaround)."""

import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
from taskiq import AckableMessage, BrokerMessage
from taskiq_redis import RedisStreamBroker

from staffroom_api.broker import ReclaimingRedisStreamBroker
from staffroom_api.settings import Settings

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _orphan_message(url: str, queue: str) -> None:
    """A consumer reads a message and dies without acknowledging it."""
    dead = RedisStreamBroker(url, queue_name=queue, consumer_name="dead-worker")
    await dead.startup()
    await dead.kick(BrokerMessage(task_id="t1", task_name="x", message=b"orphan", labels={}))
    listener = dead.listen()
    received = await anext(listener)  # read, never acked
    assert received.data == b"orphan"
    await listener.aclose()
    await dead.shutdown()


async def _first_message_within(
    listener: AsyncGenerator[AckableMessage, None], seconds: float
) -> bytes | None:
    try:
        return (await asyncio.wait_for(anext(listener), seconds)).data
    except TimeoutError:
        return None


@pytest.mark.parametrize(
    ("broker_class", "expected"),
    [
        pytest.param(ReclaimingRedisStreamBroker, b"orphan", id="our_fix_reclaims"),
        # When this case starts failing, upstream fixed the bug: delete broker.py.
        pytest.param(RedisStreamBroker, None, id="test_upstream_broker_still_has_the_bug"),
    ],
)
async def test_idle_queue_reclaims_dead_workers_message(
    broker_class: type[RedisStreamBroker], expected: bytes | None
) -> None:
    url, queue = Settings().redis_url, f"test:reclaim:{uuid.uuid4()}"
    await _orphan_message(url, queue)

    survivor = broker_class(
        url, queue_name=queue, consumer_name="survivor", idle_timeout=100, xread_block=200
    )
    await survivor.startup()
    await asyncio.sleep(0.2)  # let the orphan become idle
    listener = survivor.listen()
    try:
        assert await _first_message_within(listener, seconds=2) == expected
    finally:
        await listener.aclose()
        await survivor.shutdown()
