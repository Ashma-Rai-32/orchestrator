"""Deploy with approval (M6.3): nothing is published without the admin's yes.

Needs Docker and the sandbox image (like test_docker_sandbox.py).
"""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from staffroom_api.agents.deploy import APPROVE, SiteHost
from staffroom_api.agents.events import InputNeeded, TeamEvent
from staffroom_api.agents.models import chat_model
from staffroom_api.agents.team import EmployeeSpec, Publishing, build_team
from staffroom_api.sandbox.docker_backend import DockerSandbox

pytestmark = pytest.mark.anyio
GOAL = "Build the Bean There homepage and DEPLOY it"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def sandbox() -> Iterator[DockerSandbox]:
    box = DockerSandbox(uuid.uuid4(), uuid.uuid4(), image="staffroom-sandbox:dev")
    yield box
    box.close(keep_workspace=False)


async def run_until_approval(sandbox: DockerSandbox, sites: SiteHost) -> tuple[object, InputNeeded]:
    team = build_team(
        [EmployeeSpec("Robin", ["react"])],
        model=lambda: chat_model("fake"),
        checkpointer=InMemorySaver(),
        sandbox=sandbox,
        publishing=Publishing(sites=sites, slug="bean-there"),
    )
    events: list[TeamEvent] = [e async for e in team.stream(GOAL, thread_id="t:deploy")]
    request = events[-2]
    assert isinstance(request, InputNeeded)
    assert events[-1].type == "run_waiting"
    return team, request


async def finish(team: object, request: InputNeeded, decision: str) -> list[TeamEvent]:
    stream = team.stream(GOAL, thread_id="t:deploy", answers={request.question_id: decision})  # type: ignore[attr-defined]
    return [e async for e in stream]


async def test_approval_is_requested_with_a_preview(sandbox: DockerSandbox, tmp_path: Path) -> None:
    sites = SiteHost(tmp_path, "http://sites.test")
    _, request = await run_until_approval(sandbox, sites)

    assert request.kind == "approval"
    assert request.preview_url and request.preview_url.startswith("http://sites.test/previews/")
    token = request.preview_url.rstrip("/").rsplit("/", 1)[-1]
    assert "Bean There" in (tmp_path / "previews" / token / "index.html").read_text()
    assert not (tmp_path / "sites" / "bean-there").exists()  # nothing public yet


async def test_rejected_site_is_not_published(sandbox: DockerSandbox, tmp_path: Path) -> None:
    sites = SiteHost(tmp_path, "http://sites.test")
    team, request = await run_until_approval(sandbox, sites)

    events = await finish(team, request, "Rejected by the admin. Feedback: make it warmer")
    assert not (tmp_path / "sites" / "bean-there").exists()
    results = " ".join(getattr(e, "result", "") for e in events)
    assert "did not approve" in results and "make it warmer" in results


async def test_approved_site_is_published(sandbox: DockerSandbox, tmp_path: Path) -> None:
    sites = SiteHost(tmp_path, "http://sites.test")
    team, request = await run_until_approval(sandbox, sites)

    events = await finish(team, request, APPROVE)
    assert "Bean There" in (tmp_path / "sites" / "bean-there" / "index.html").read_text()
    results = " ".join(getattr(e, "result", "") for e in events)
    assert "Published at http://sites.test/sites/bean-there/" in results
    assert events[-1].type == "run_finished"


async def test_previews_of_different_runs_never_collide(tmp_path: Path) -> None:
    """Fake tool-call ids repeat ("call_0"): tokens must still differ per run."""
    sites = SiteHost(tmp_path, "http://sites.test")
    urls = []
    for thread in ("tenant-a:run-1", "tenant-b:run-2"):
        box = DockerSandbox(uuid.uuid4(), uuid.uuid4(), image="staffroom-sandbox:dev")
        try:
            team = build_team(
                [EmployeeSpec("Robin", ["react"])],
                model=lambda: chat_model("fake"),
                checkpointer=InMemorySaver(),
                sandbox=box,
                publishing=Publishing(sites=sites, slug="x"),
            )
            events = [e async for e in team.stream(GOAL, thread_id=thread)]
            request = events[-2]
            assert isinstance(request, InputNeeded)
            urls.append(request.preview_url)
        finally:
            box.close(keep_workspace=False)
    assert urls[0] != urls[1]
