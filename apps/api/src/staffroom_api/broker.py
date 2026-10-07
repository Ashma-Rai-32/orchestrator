"""Workarounds for taskiq-redis `RedisStreamBroker.listen`; delete when upstream is fixed.

taskiq-redis 1.2.4 (`RedisStreamBroker.listen`) does `if not fetched: continue`
before its XAUTOCLAIM block, so on an idle queue a dead worker's message is never
reclaimed; only the arrival of a new message triggers it (ADR-0004, update).

This subclass runs the same reclaim on every loop iteration, and survives a timed-out
or dropped blocking read instead of crashing the worker process. The logic is
upstream's, reordered. `tests/test_broker.py::test_upstream_broker_still_has_the_bug`
fails once upstream fixes it: that is the signal to delete this module.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from taskiq import AckableMessage
from taskiq_redis import RedisStreamBroker

log = logging.getLogger(__name__)


class ReclaimingRedisStreamBroker(RedisStreamBroker):
    async def listen(self) -> AsyncGenerator[AckableMessage, None]:
        async with Redis(connection_pool=self.connection_pool) as redis_conn:
            streams: Any = {self.queue_name: ">", **self.additional_streams}  # as upstream
            while True:
                try:
                    fetched: Any = await redis_conn.xreadgroup(
                        self.consumer_group_name,
                        self.consumer_name,
                        streams,
                        block=self.block,
                        noack=False,
                        count=self.count,
                    )
                except (RedisTimeoutError, RedisConnectionError) as exc:
                    # Second fix (found with a real local model saturating the CPU): a slow
                    # blocking read raised, killing the worker process and the run inside
                    # it. For a poll, a timeout means "no message yet"; keep listening.
                    log.warning("queue read failed (%s); retrying", type(exc).__name__)
                    continue
                for stream, messages in fetched or []:
                    for msg_id, msg in messages:
                        yield self._ackable(stream, msg_id, msg)
                # The fix: reclaim even when no new message arrived.
                async for message in self._reclaim_stale(redis_conn):
                    yield message

    async def _reclaim_stale(self, redis_conn: Redis) -> AsyncGenerator[AckableMessage, None]:
        for stream in [self.queue_name, *self.additional_streams.keys()]:
            pipe = redis_conn.pipeline()
            lock = pipe.lock(
                f"autoclaim:{self.consumer_group_name}:{stream}",
                timeout=self.unacknowledged_lock_timeout,
            )
            await lock.acquire()
            await pipe.xautoclaim(
                name=stream,
                groupname=self.consumer_group_name,
                consumername=self.consumer_name,
                min_idle_time=self.idle_timeout,
                count=self.unacknowledged_batch_size,
            )
            await lock.release()
            results: Any = await pipe.execute()
            for msg_id, msg in results[1][1]:
                yield self._ackable(stream, msg_id, msg)

    def _ackable(self, stream: Any, msg_id: Any, msg: Any) -> AckableMessage:
        return AckableMessage(
            data=msg[b"data"], ack=self._ack_generator(id=msg_id, queue_name=stream)
        )
