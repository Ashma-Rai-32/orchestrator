"""Playwright MCP inside the sandbox, as LangChain tools (needs Docker + sandbox image)."""

import uuid
from collections.abc import Iterator

import pytest

from staffroom_api.agents.models import chat_model
from staffroom_api.agents.team import EmployeeSpec, build_team, toolsets_needed
from staffroom_api.agents.toolsets import open_toolsets
from staffroom_api.sandbox.browser import ALLOWED_TOOLS, browser_tools
from staffroom_api.sandbox.docker_backend import DockerSandbox

pytestmark = pytest.mark.anyio

PAGE = (
    "<html><head><title>Acme AI</title></head>"
    "<body><h1>Chat with Acme AI</h1>"
    "<input aria-label='Message'><button>Send</button></body></html>"
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def site() -> Iterator[DockerSandbox]:
    sandbox = DockerSandbox(uuid.uuid4(), uuid.uuid4(), image="staffroom-sandbox:dev")
    sandbox.write("/workspace/site/index.html", PAGE)
    sandbox.execute("cd /workspace/site && (nohup python3 -m http.server 4173 >/dev/null 2>&1 &)")
    yield sandbox
    sandbox.close(keep_workspace=False)


async def test_browser_sees_the_site_built_in_the_sandbox(site: DockerSandbox) -> None:
    async with browser_tools(site.id) as tools:
        by_name = {t.name: t for t in tools}
        await by_name["browser_wait_for"].ainvoke({"time": 1})
        await by_name["browser_navigate"].ainvoke({"url": "http://localhost:4173/"})
        snapshot = str(await by_name["browser_snapshot"].ainvoke({}))

    assert 'heading "Chat with Acme AI"' in snapshot
    assert 'button "Send"' in snapshot


async def test_only_curated_tools_are_offered(site: DockerSandbox) -> None:
    async with browser_tools(site.id) as tools:
        names = {t.name for t in tools}
    assert names <= ALLOWED_TOOLS
    assert "browser_run_code_unsafe" not in names
    assert {"browser_navigate", "browser_snapshot", "browser_click"} <= names


async def test_tester_checks_colleagues_work_in_a_browser() -> None:
    """Builder writes a page; the `testing` employee serves it and reads it in Chromium."""
    sandbox = DockerSandbox(uuid.uuid4(), uuid.uuid4(), image="staffroom-sandbox:dev")
    team_members = [EmployeeSpec("Robin", ["react"]), EmployeeSpec("Tess", ["testing"])]
    try:
        assert toolsets_needed(team_members) == {"browser"}
        async with open_toolsets(toolsets_needed(team_members), sandbox) as toolsets:
            team = build_team(
                team_members,
                model=lambda: chat_model("fake"),
                sandbox=sandbox,
                toolsets=toolsets,
            )
            result = await team.run("Build a landing page")
    finally:
        sandbox.close(keep_workspace=False)

    by_employee = {a.employee: a for a in result.assignments}
    assert list(by_employee) == ["Robin", "Tess"]  # built first, then tested
    assert "the site lists 1 page(s)" in by_employee["Tess"].result  # one builder, one page
    assert "type" not in by_employee["Tess"].result  # plain text, not content-block repr
    assert ".html" in by_employee["Tess"].result
