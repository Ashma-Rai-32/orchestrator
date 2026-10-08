"""OpenBao secret store (ADR-0009) against a real OpenBao in dev mode."""

import uuid
from collections.abc import Iterator

import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy

from staffroom_api.secrets import InvalidSecretName, OpenBaoSecretStore

pytestmark = pytest.mark.anyio
DEV_TOKEN = "test-root"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def openbao_url() -> Iterator[str]:
    container = (
        DockerContainer("openbao/openbao:2.7.1")
        .with_command(
            f"server -dev -dev-root-token-id={DEV_TOKEN} -dev-listen-address=0.0.0.0:8200"
        )
        .with_exposed_ports(8200)
        .waiting_for(HttpWaitStrategy(8200, "/v1/sys/health").for_status_code(200))
    )
    with container:
        yield f"http://{container.get_container_host_ip()}:{container.get_exposed_port(8200)}"


@pytest.fixture
def store(openbao_url: str) -> OpenBaoSecretStore:
    return OpenBaoSecretStore(openbao_url, DEV_TOKEN)


async def test_put_then_get(store: OpenBaoSecretStore) -> None:
    acme = uuid.uuid4()
    await store.put(acme, "OPENAI_API_KEY", "sk-test-value")
    assert await store.get(acme, "OPENAI_API_KEY") == "sk-test-value"
    assert await store.names(acme) == ["OPENAI_API_KEY"]


async def test_tenants_do_not_see_each_others_secrets(store: OpenBaoSecretStore) -> None:
    acme, globex = uuid.uuid4(), uuid.uuid4()
    await store.put(acme, "STRIPE_KEY", "acme-only")
    assert await store.get(globex, "STRIPE_KEY") is None
    assert await store.names(globex) == []


async def test_overwriting_keeps_the_latest_value(store: OpenBaoSecretStore) -> None:
    acme = uuid.uuid4()
    await store.put(acme, "API_TOKEN", "v1")
    await store.put(acme, "API_TOKEN", "v2")  # KV v2 keeps v1 as an older version
    assert await store.get(acme, "API_TOKEN") == "v2"


@pytest.mark.parametrize("bad", ["openai_key", "1KEY", "MY-KEY", "A", "../../escape"])
async def test_names_must_be_env_var_style(store: OpenBaoSecretStore, bad: str) -> None:
    with pytest.raises(InvalidSecretName):
        await store.put(uuid.uuid4(), bad, "x")
