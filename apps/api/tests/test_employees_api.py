"""Hiring employees through the HTTP API, against real Postgres with RLS."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from staffroom_api.main import create_app
from staffroom_api.settings import Settings


@pytest.fixture
def client(api_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(api_settings)) as c:
        yield c


def new_tenant(client: TestClient, name: str) -> dict[str, str]:
    response = client.post("/tenants", json={"name": name})
    assert response.status_code == 201
    return {"X-Tenant-ID": response.json()["id"]}


def test_skill_catalog_is_listed(client: TestClient) -> None:
    keys = {s["key"] for s in client.get("/skills").json()}
    assert {"react", "nodejs", "ai-integration"} <= keys


def test_hire_and_list_employees(client: TestClient) -> None:
    acme = new_tenant(client, "Acme")
    hired = client.post(
        "/employees", json={"name": "Robin", "skills": ["react", "css", "react"]}, headers=acme
    )
    assert hired.status_code == 201
    assert hired.json()["skills"] == ["css", "react"]  # de-duplicated, stable order

    names = [e["name"] for e in client.get("/employees", headers=acme).json()]
    assert names == ["Robin"]


def test_tenants_only_see_their_own_employees(client: TestClient) -> None:
    acme, globex = new_tenant(client, "Acme"), new_tenant(client, "Globex")
    client.post("/employees", json={"name": "Robin", "skills": ["react"]}, headers=acme)
    client.post("/employees", json={"name": "Kim", "skills": ["python"]}, headers=globex)

    assert [e["name"] for e in client.get("/employees", headers=acme).json()] == ["Robin"]
    assert [e["name"] for e in client.get("/employees", headers=globex).json()] == ["Kim"]


def test_unknown_skill_is_rejected(client: TestClient) -> None:
    acme = new_tenant(client, "Acme")
    response = client.post(
        "/employees", json={"name": "Max", "skills": ["react", "cobol"]}, headers=acme
    )
    assert response.status_code == 422
    assert "cobol" in response.json()["detail"]


def test_unknown_tenant_sees_nothing_and_cannot_hire(client: TestClient) -> None:
    stranger = {"X-Tenant-ID": str(uuid.uuid4())}
    assert client.get("/employees", headers=stranger).json() == []
    # The database refuses (no such tenant). Surfaces as a 500 only while the
    # header stub exists; with auth the tenant comes from a verified token.
    with pytest.raises(IntegrityError, match="fk_employees_tenant_id_tenants"):
        client.post("/employees", json={"name": "Spy", "skills": ["react"]}, headers=stranger)


def test_run_goal_with_hired_team(client: TestClient) -> None:
    acme = new_tenant(client, "Acme")
    assert client.post("/goals", json={"goal": "Build a site"}, headers=acme).status_code == 409

    for name, skills in [("Robin", ["react"]), ("Sam", ["react"]), ("Ada", ["nodejs"])]:
        client.post("/employees", json={"name": name, "skills": skills}, headers=acme)
    result = client.post("/goals", json={"goal": "Build a site"}, headers=acme).json()

    assert {a["employee"] for a in result["assignments"]} == {"Robin", "Ada"}
    assert result["summary"].startswith("All done.")


def test_missing_tenant_header_is_rejected(client: TestClient) -> None:
    assert client.get("/employees").status_code == 422
