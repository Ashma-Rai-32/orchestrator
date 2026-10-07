# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx==0.28.1", "websockets==17.2"]
# ///
"""Dev tool: sign in as a demo founder, hire a small team, start a goal, print events live.

    uv run scripts/watch_run.py "Build me an LLM wrapper website"
    uv run scripts/watch_run.py --as founder@globex.test "Build a landing page"
    uv run scripts/watch_run.py --as founder@initech.test --team duo "..."   # small team, local models
"""

import argparse
import asyncio
import json
import time

import httpx
import websockets

API = "http://localhost:8000"
TOKEN_URL = "http://localhost:8080/realms/staffroom/protocol/openid-connect/token"
TEAMS = {
    "full": [
        ("Pixel 1", ["react", "css"]),
        ("Pixel 2", ["react", "css"]),
        ("Ada", ["nodejs", "ai-integration"]),
        ("Tess", ["testing"]),  # checks the built site in a real browser
    ],
    # For slow local models: one builder + one tester (fewer, shorter model calls).
    "duo": [("Pixel 1", ["react", "css"]), ("Tess", ["testing"])],
}


async def sign_in(http: httpx.AsyncClient, username: str) -> str:
    # DEV ONLY client with password grant (see infra/keycloak/staffroom-realm.json).
    response = await http.post(TOKEN_URL, data={
        "grant_type": "password", "client_id": "staffroom-dev-cli",
        "username": username, "password": "staffroom-dev", "scope": "openid organization",
    })
    response.raise_for_status()
    return str(response.json()["access_token"])


async def main(goal: str, username: str, team: str) -> None:
    async with httpx.AsyncClient(base_url=API) as http:
        token = await sign_in(http, username)
        auth = {"Authorization": f"Bearer {token}"}
        me = (await http.get("/me", headers=auth)).json()
        print(f"signed in as {username}, tenant {me['tenant_name']} ({me['tenant_id']})")
        hired = {e["name"] for e in (await http.get("/employees", headers=auth)).json()}
        for name, skills in TEAMS[team]:
            if name not in hired:
                await http.post("/employees", json={"name": name, "skills": skills}, headers=auth)
        run = (await http.post("/goals", json={"goal": goal}, headers=auth)).json()

    print(f"run {run['id']} ({run['status']}), streaming:\n")
    start = time.monotonic()
    url = f"ws://localhost:8000/runs/{run['id']}/stream"
    # Token travels as a WebSocket subprotocol, not in the URL (URLs end up in logs).
    async with websockets.connect(url, subprotocols=["bearer", token]) as ws:
        async for message in ws:
            event = json.loads(message)["event"]
            details = ", ".join(f"{k}={v!r}" for k, v in event.items() if k != "type")
            print(f"  t={time.monotonic() - start:4.1f}s  {event['type']:<14} {details[:150]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("goal", nargs="?", default="Build me an LLM wrapper website")
    parser.add_argument("--as", dest="username", default="founder@acme.test")
    parser.add_argument("--team", choices=TEAMS, default="full", help="who to hire if missing")
    args = parser.parse_args()
    asyncio.run(main(args.goal, args.username, args.team))
