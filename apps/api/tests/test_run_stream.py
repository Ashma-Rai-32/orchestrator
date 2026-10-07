"""WebSocket run stream: replay + live via Redis Streams, Postgres fallback, isolation."""

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis import Redis
from starlette.websockets import WebSocketDisconnect

from staffroom_api.event_stream import stream_key
from staffroom_api.settings import Settings
from tests.helpers import new_tenant, start_run


def collect(client: TestClient, run_id: str, token: str | None) -> list[dict[str, Any]]:
    protocols = ["bearer", token] if token else []
    received: list[dict[str, Any]] = []
    with client.websocket_connect(f"/runs/{run_id}/stream", subprotocols=protocols) as ws:
        try:
            while True:
                received.append(ws.receive_json())
        except WebSocketDisconnect:
            pass  # server closes after the terminal event
    return received


def test_late_subscriber_gets_full_replay_then_close(client: TestClient) -> None:
    acme = new_tenant(client, "Acme")
    run_id = start_run(client, acme)  # TestClient finishes the run before returning

    received = collect(client, run_id, acme.token)
    types = [m["event"]["type"] for m in received]
    assert types[0] == "run_started"
    assert types[-1] == "run_finished"
    assert types.count("task_finished") == 2
    ids = [m["id"] for m in received]
    assert ids == sorted(ids)  # same ids as GET /runs/{id}/events, in order


def test_replays_from_postgres_when_live_feed_expired(
    client: TestClient, api_settings: Settings
) -> None:
    acme = new_tenant(client, "Acme")
    run_id = start_run(client, acme)
    redis = Redis(host=api_settings.redis_host, port=api_settings.redis_port)
    redis.delete(stream_key(acme.id, uuid.UUID(run_id)))

    from_postgres = collect(client, run_id, acme.token)
    from_rest = client.get(f"/runs/{run_id}/events", headers=acme).json()
    assert [m["id"] for m in from_postgres] == [e["id"] for e in from_rest]


def test_other_tenant_cannot_subscribe(client: TestClient) -> None:
    acme, globex = new_tenant(client, "Acme"), new_tenant(client, "Globex")
    run_id = start_run(client, acme)

    with pytest.raises(WebSocketDisconnect) as closed:
        collect(client, run_id, globex.token)
    assert closed.value.code == 4404


def test_stream_requires_a_token(client: TestClient) -> None:
    acme = new_tenant(client, "Acme")
    run_id = start_run(client, acme)
    with pytest.raises(WebSocketDisconnect) as closed:
        collect(client, run_id, token=None)
    assert closed.value.code == 4401


@pytest.mark.anyio
async def test_follow_survives_redis_read_timeouts() -> None:
    """Live finding: long gaps between events (real models) made a read time out."""
    from redis.exceptions import TimeoutError as RedisTimeoutError

    from staffroom_api import event_stream

    finished = json.dumps({"id": 1, "event": {"type": "run_finished", "summary": "ok"}})

    class FlakyRedis:
        calls = 0

        async def xread(self, *args: Any, **kwargs: Any) -> Any:
            FlakyRedis.calls += 1
            if FlakyRedis.calls == 1:
                raise RedisTimeoutError("Timeout reading from redis:6379")
            return [(b"key", [(b"1-0", {b"event": finished.encode()})])]

    events = [p async for p in event_stream.follow(FlakyRedis(), uuid.uuid4(), uuid.uuid4())]  # type: ignore[arg-type]
    assert [e["event"]["type"] for e in events] == ["run_finished"]
    assert FlakyRedis.calls == 2


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
