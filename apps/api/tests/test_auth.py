"""Token verification (ADR-0003): what gets in, and what is rejected."""

import time
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from tests.helpers import mint, new_tenant


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def one_org() -> dict[str, dict[str, str]]:
    return {"acme": {"id": str(uuid.uuid4())}}


def test_first_request_creates_the_tenant(client: TestClient) -> None:
    acme = new_tenant(client, "Acme")  # asserts /me returns the token's org id
    assert client.get("/employees", headers=acme).json() == []


def test_no_token_is_401(client: TestClient) -> None:
    response = client.get("/employees")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(
            mint(one_org(), key=rsa.generate_private_key(public_exponent=65537, key_size=2048)),
            id="signed_by_another_key",
        ),
        pytest.param(mint(one_org(), exp=int(time.time()) - 10), id="expired"),
        pytest.param(mint(one_org(), aud="someone-else"), id="wrong_audience"),
        pytest.param(mint(one_org(), iss="http://evil.test/realms/x"), id="wrong_issuer"),
        pytest.param("not-a-jwt", id="garbage"),
    ],
)
def test_invalid_tokens_are_401(client: TestClient, token: str) -> None:
    response = client.get("/employees", headers=bearer(token))
    assert response.status_code == 401
    assert token not in response.text  # never echo credentials


@pytest.mark.parametrize(
    "tenants",
    [
        pytest.param({}, id="no_organization"),
        pytest.param(
            {"acme": {"id": str(uuid.uuid4())}, "globex": {"id": str(uuid.uuid4())}},
            id="two_organizations",
        ),
    ],
)
def test_token_must_name_exactly_one_organization(
    client: TestClient, tenants: dict[str, dict[str, str]]
) -> None:
    response = client.get("/employees", headers=bearer(mint(tenants)))
    assert response.status_code == 403
    assert "exactly one organization" in response.json()["detail"]
