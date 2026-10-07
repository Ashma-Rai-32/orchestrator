"""Docker sandbox backend (ADR-0006), exercised through deepagents' own file API.

Needs a local Docker daemon and the image: docker build -t staffroom-sandbox:dev sandbox/
"""

import uuid
from collections.abc import Iterator

import docker
import pytest

from staffroom_api.agents.models import chat_model
from staffroom_api.agents.team import EmployeeSpec, build_team
from staffroom_api.sandbox.docker_backend import DockerSandbox

IMAGE = "staffroom-sandbox:dev"


@pytest.fixture
def run_id() -> Iterator[uuid.UUID]:
    rid = uuid.uuid4()
    yield rid
    client = docker.from_env()  # clean up whatever the test left behind
    for container in client.containers.list(all=True, filters={"label": f"staffroom.run={rid}"}):
        container.remove(force=True)
    for volume in client.volumes.list(filters={"label": f"staffroom.run={rid}"}):
        volume.remove()


@pytest.fixture
def sandbox(run_id: uuid.UUID) -> DockerSandbox:
    return DockerSandbox(uuid.uuid4(), run_id, image=IMAGE)


def test_execute_runs_node(sandbox: DockerSandbox) -> None:
    result = sandbox.execute('node -e "console.log(6 * 7)"')
    assert (result.output.strip(), result.exit_code) == ("42", 0)


def test_deepagents_file_tools_work_on_top(sandbox: DockerSandbox) -> None:
    # write/read/edit are deepagents' BaseSandbox helpers built on our 4 primitives.
    assert sandbox.write("/workspace/site/index.html", "<h1>Hello</h1>\n").error is None
    assert sandbox.edit("/workspace/site/index.html", "Hello", "Staffroom").error is None
    assert "<h1>Staffroom</h1>" in str(sandbox.read("/workspace/site/index.html"))
    assert sandbox.download_files(["/workspace/site"])[0].error == "is_directory"
    assert sandbox.download_files(["/workspace/nope.txt"])[0].error == "file_not_found"


def test_hardening(sandbox: DockerSandbox) -> None:
    assert sandbox.execute("id -u").output.strip() == "1000"  # not root
    assert sandbox.execute("touch /etc/evil").exit_code != 0  # read-only root fs
    cap_eff = sandbox.execute("grep CapEff /proc/self/status").output.split()[-1]
    assert int(cap_eff, 16) == 0  # no Linux capabilities at all


def test_commands_are_time_limited(sandbox: DockerSandbox) -> None:
    assert sandbox.execute("sleep 10", timeout=1).exit_code == 124  # coreutils timeout


def test_workspace_survives_container_loss(run_id: uuid.UUID) -> None:
    tenant = uuid.uuid4()
    first = DockerSandbox(tenant, run_id, image=IMAGE)
    first.write("/workspace/notes.md", "keep me\n")
    first.close()  # container gone (e.g. worker crash cleanup); volume kept

    second = DockerSandbox(tenant, run_id, image=IMAGE)
    assert "keep me" in str(second.read("/workspace/notes.md"))


@pytest.mark.anyio
async def test_employees_use_the_sandbox_during_a_run(sandbox: DockerSandbox) -> None:
    team = build_team(
        [EmployeeSpec("Robin", ["react"]), EmployeeSpec("Ada", ["nodejs"])],
        model=lambda: chat_model("fake"),
        sandbox=sandbox,
    )
    result = await team.run("Build a site")

    # Each employee wrote a page via write_file, then ran node via execute.
    pages = sandbox.execute("ls /workspace/site").output.split()
    assert len(pages) == 2
    assert all("site pages:" in a.result for a in result.assignments)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
