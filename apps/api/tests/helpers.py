"""Test helpers: tokens signed by a throwaway key, standing in for Keycloak."""

import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from staffroom_api.auth import TokenVerifier

ISSUER = "http://keycloak.test/realms/staffroom"
AUDIENCE = "staffroom-api"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_verifier() -> TokenVerifier:
    public_key = _KEY.public_key()
    return TokenVerifier(ISSUER, AUDIENCE, key_for=lambda _token: public_key)


def mint(tenants: dict[str, Any] | None = None, *, key: Any = None, **overrides: Any) -> str:
    """A Keycloak-shaped access token. `tenants` mirrors the organization mapper claim."""
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(uuid.uuid4()),
        "iat": now,
        "exp": now + 300,
        "tenants": tenants if tenants is not None else {},
        **overrides,
    }
    return jwt.encode(claims, key or _KEY, algorithm="RS256")


class TenantAuth(dict[str, str]):
    """Usable directly as request headers; also carries the tenant id and raw token."""

    def __init__(self, tenant_id: uuid.UUID, token: str) -> None:
        super().__init__({"Authorization": f"Bearer {token}"})
        self.id, self.token = tenant_id, token


def new_tenant(client: TestClient, name: str) -> TenantAuth:
    """A founder of a brand-new organization; their first request creates the tenant."""
    tenant_id = uuid.uuid4()
    auth = TenantAuth(tenant_id, mint({name.lower(): {"id": str(tenant_id)}}))
    assert client.get("/me", headers=auth).json()["tenant_id"] == str(tenant_id)
    return auth


def start_run(client: TestClient, tenant: dict[str, str], goal: str = "Build a site") -> str:
    client.post("/employees", json={"name": "Robin", "skills": ["react"]}, headers=tenant)
    client.post("/employees", json={"name": "Ada", "skills": ["nodejs"]}, headers=tenant)
    response = client.post("/goals", json={"goal": goal}, headers=tenant)
    assert response.status_code == 202
    return str(response.json()["id"])
