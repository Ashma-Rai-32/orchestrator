from fastapi.testclient import TestClient


def new_tenant(client: TestClient, name: str) -> dict[str, str]:
    """Create a tenant via the API; returns the (stub) auth header for it."""
    response = client.post("/tenants", json={"name": name})
    assert response.status_code == 201
    return {"X-Tenant-ID": response.json()["id"]}


def start_run(client: TestClient, tenant: dict[str, str], goal: str = "Build a site") -> str:
    client.post("/employees", json={"name": "Robin", "skills": ["react"]}, headers=tenant)
    client.post("/employees", json={"name": "Ada", "skills": ["nodejs"]}, headers=tenant)
    response = client.post("/goals", json={"goal": goal}, headers=tenant)
    assert response.status_code == 202
    return str(response.json()["id"])
