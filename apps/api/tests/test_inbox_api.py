"""Admin inbox end to end over HTTP: ask -> waiting -> answer -> resumed -> finished."""

from fastapi.testclient import TestClient

from tests.helpers import new_tenant


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
