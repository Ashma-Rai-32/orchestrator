"""Admin inbox end to end over HTTP: ask -> waiting -> answer -> resumed -> finished."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from staffroom_api.main import create_app
from staffroom_api.settings import Settings
from tests.helpers import fake_verifier, new_tenant


def start_asking_run(client: TestClient, tenant: dict[str, str]) -> str:
    client.post("/employees", json={"name": "Robin", "skills": ["react"]}, headers=tenant)
    goal = "Build a site. ASK: which colour should the buttons be?"
    return str(client.post("/goals", json={"goal": goal}, headers=tenant).json()["id"])


def test_question_pauses_the_run_and_the_answer_resumes_it(client: TestClient) -> None:
    acme = new_tenant(client, "Acme")
    run_id = start_asking_run(client, acme)

    assert client.get(f"/runs/{run_id}", headers=acme).json()["status"] == "waiting"
    inbox = client.get("/inbox", headers=acme).json()
    assert [(q["employee"], q["question"]) for q in inbox] == [
        ("Robin", "which colour should the buttons be?")
    ]

    result = client.post(f"/inbox/{inbox[0]['id']}/answer", json={"answer": "teal"}, headers=acme)
    assert result.status_code == 200
    assert result.json()["run_resumed"] is True

    run = client.get(f"/runs/{run_id}", headers=acme).json()
    assert run["status"] == "succeeded"
    assert client.get("/inbox", headers=acme).json() == []
    events = [e["event"] for e in client.get(f"/runs/{run_id}/events", headers=acme).json()]
    types = [e["type"] for e in events]
    assert types.index("run_waiting") < types.index("run_resumed") < types.index("run_finished")
    assert any("The admin answered: teal" in e.get("result", "") for e in events)


def test_answering_twice_is_rejected(client: TestClient) -> None:
    acme = new_tenant(client, "Acme")
    start_asking_run(client, acme)
    item = client.get("/inbox", headers=acme).json()[0]
    client.post(f"/inbox/{item['id']}/answer", json={"answer": "teal"}, headers=acme)

    again = client.post(f"/inbox/{item['id']}/answer", json={"answer": "red"}, headers=acme)
    assert again.status_code == 409


def test_other_tenants_cannot_see_or_answer_questions(client: TestClient) -> None:
    acme, globex = new_tenant(client, "Acme"), new_tenant(client, "Globex")
    start_asking_run(client, acme)
    item = client.get("/inbox", headers=acme).json()[0]

    assert client.get("/inbox", headers=globex).json() == []
    stolen = client.post(f"/inbox/{item['id']}/answer", json={"answer": "x"}, headers=globex)
    assert stolen.status_code == 404


class MemorySecretStore:
    """SecretStore stand-in (OpenBao itself is covered in test_secrets.py)."""

    def __init__(self) -> None:
        self.values: dict[tuple[uuid.UUID, str], str] = {}

    async def put(self, tenant_id: uuid.UUID, name: str, value: str) -> None:
        self.values[(tenant_id, name)] = value

    async def get(self, tenant_id: uuid.UUID, name: str) -> str | None:
        return self.values.get((tenant_id, name))

    async def names(self, tenant_id: uuid.UUID) -> list[str]:
        return sorted(n for t, n in self.values if t == tenant_id)


def test_a_secret_answer_goes_to_the_store_and_nowhere_else(api_settings: Settings) -> None:
    secrets = MemorySecretStore()
    value = "sk-test-0123456789abcdefSECRET"
    with TestClient(create_app(api_settings, verifier=fake_verifier(), secrets=secrets)) as client:
        acme = new_tenant(client, "Acme")
        client.post("/employees", json={"name": "Ada", "skills": ["nodejs"]}, headers=acme)
        goal = "Wire up the chatbot. ASK: I need the LLM provider key SECRET: OPENAI_API_KEY"
        run_id = client.post("/goals", json={"goal": goal}, headers=acme).json()["id"]

        item = client.get("/inbox", headers=acme).json()[0]
        assert item["secret_name"] == "OPENAI_API_KEY"
        client.post(f"/inbox/{item['id']}/answer", json={"answer": value}, headers=acme)

        assert secrets.values == {(acme.id, "OPENAI_API_KEY"): value}
        assert client.get(f"/runs/{run_id}", headers=acme).json()["status"] == "succeeded"
        events = client.get(f"/runs/{run_id}/events", headers=acme).text
        assert value not in events  # never in any event the UI or Redis sees
        assert "Stored securely as OPENAI_API_KEY" in events  # the employee got the name

    engine = create_engine(_owner_url(api_settings))
    with engine.connect() as conn:  # never in the inbox table either
        stored = (
            conn.execute(text("SELECT answer FROM inbox_items WHERE secret_name IS NOT NULL"))
            .scalars()
            .all()
        )
    engine.dispose()
    assert stored and all(value not in a for a in stored)


def test_secret_questions_need_a_secret_store(client: TestClient) -> None:
    acme = new_tenant(client, "Acme")
    client.post("/employees", json={"name": "Ada", "skills": ["nodejs"]}, headers=acme)
    goal = "Wire up the chatbot. ASK: I need the LLM provider key SECRET: OPENAI_API_KEY"
    client.post("/goals", json={"goal": goal}, headers=acme)
    item = client.get("/inbox", headers=acme).json()[0]

    response = client.post(f"/inbox/{item['id']}/answer", json={"answer": "x"}, headers=acme)
    assert response.status_code == 503  # no store configured: refuse rather than leak


def _owner_url(settings: Settings) -> str:
    host, port = settings.postgres_host, settings.postgres_port
    return f"postgresql+psycopg://test:test@{host}:{port}/{settings.postgres_db}"
