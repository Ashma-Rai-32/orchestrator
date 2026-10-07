# 0004. Task queue: Taskiq on Redis Streams

- Status: accepted
- Date: 2026-10-07

## Context and problem

Runs must leave the API process: they take minutes to hours and must continue while the admin is logged out and across API restarts. The brief: a task queue only **triggers** runs; durability comes from the LangGraph checkpointer. Our code is async end to end (FastAPI, SQLAlchemy asyncio, LangGraph `astream`).

## Decision drivers

- Native asyncio (no `asyncio.run()` per task, no sync bridge).
- Redelivery when a worker dies (message acknowledged only after the task ends).
- Redis as broker (already in the stack).
- Deterministic tests without a running broker.
- Actively maintained.

## Options considered (versions and source checked 2026-10-07)

1. **Celery 5.6.3**: very mature, active. No asyncio support in the task API (none in `celery/app/task.py`); async code would need `asyncio.run()` per task.
2. **Dramatiq 2.2.1**: active, reliable acks. `async def` actors are wrapped with `async_to_sync` onto a shared event-loop thread (`dramatiq/actor.py`): works, but it is a bridge.
3. **arq 0.28.0**: asyncio-native, but its README states "in maintenance only mode".
4. **Taskiq 0.13.0 + taskiq-redis 1.2.4**: asyncio-native, active (21 releases in 2 years). `RedisStreamBroker` uses consumer groups, acknowledges after execution by default (`WHEN_SAVED`), and re-claims unacknowledged messages with `XAUTOCLAIM` after `idle_timeout`. `InMemoryBroker(await_inplace=True)` runs tasks inline for tests.

## Decision

Option 4, Taskiq with `RedisStreamBroker`.

- One task = one **segment** of a run: it executes until the run finishes or pauses (interrupt). Waiting for a human never holds a queue message; the answer enqueues a new segment.
- Each segment has a hard timeout shorter than `idle_timeout`, so a healthy segment is never re-claimed while still running; a dead worker's segment is re-claimed after `idle_timeout`.
- Tasks are idempotent at the edge: a segment for a run already `succeeded`/`failed` exits immediately.
- Tests use `InMemoryBroker(await_inplace=True)`, selected by `TASK_BROKER=memory`.

## Consequences

- Good: no sync/async bridging; worker reuses the same async code as the API.
- Good: crash recovery is the broker's job (XAUTOCLAIM), resume is the checkpointer's job (increment 4b).
- Bad: recovery latency after a crash equals `idle_timeout` (configurable; production value to tune).
- Bad: Taskiq is younger than Celery; fewer operational tools (no Flower equivalent). Mitigated: run status and events are already in Postgres.

## Update 2026-10-07: reclaim only happens when new messages arrive

Found in the crash demo and confirmed in source (taskiq-redis 1.2.4 and upstream `main`): `RedisStreamBroker.listen()` does `if not fetched: continue` *before* its `XAUTOCLAIM` block. On an idle queue, a dead worker's message is never reclaimed; it is reclaimed only after some new message arrives. Resume itself works (verified: `run_resumed` → only the summary step re-ran).

Fix: `staffroom_api/broker.py`, a subclass of `RedisStreamBroker` that runs the same reclaim on every loop iteration (upstream logic, reordered). Verified live: with no new messages, a killed worker's run resumed after the idle window. `tests/test_broker.py` also asserts the upstream broker still has the bug; when that test fails, upstream is fixed and the subclass should be deleted. Upstream issue: to be filed by the maintainer.

## Sources

- PyPI metadata and installed source of celery 5.6.3, dramatiq 2.2.1, arq 0.28.0 (README), taskiq 0.13.0 (`acks.py`, `receiver/receiver.py`, `brokers/inmemory_broker.py`), taskiq-redis 1.2.4 (`redis_broker.py`).
