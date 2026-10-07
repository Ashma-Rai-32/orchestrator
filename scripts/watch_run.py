# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx==0.28.1", "websockets==17.2"]
# ///
"""Dev tool: create a demo tenant + team, start a goal, and print its events live.

    uv run scripts/watch_run.py "Build me an LLM wrapper website"
"""

import asyncio
import json
import sys
import time

import httpx
import websockets

API = "http://localhost:8000"


async def main(goal: str) -> None:
    async with httpx.AsyncClient(base_url=API) as http:
        tenant = (await http.post("/tenants", json={"name": "Watch demo"})).json()["id"]
        headers = {"X-Tenant-ID": tenant}
        team = [("Pixel 1", ["react", "css"]), ("Pixel 2", ["react", "css"]), ("Ada", ["nodejs", "ai-integration"])]
        for name, skills in team:
            await http.post("/employees", json={"name": name, "skills": skills}, headers=headers)
        run = (await http.post("/goals", json={"goal": goal}, headers=headers)).json()

    print(f"run {run['id']} ({run['status']}), streaming:\n")
    start = time.monotonic()
    url = f"ws://localhost:8000/runs/{run['id']}/stream?tenant_id={tenant}"
    async with websockets.connect(url) as ws:
        async for message in ws:
            event = json.loads(message)["event"]
            details = ", ".join(f"{k}={v!r}" for k, v in event.items() if k != "type")
            print(f"  t={time.monotonic() - start:4.1f}s  {event['type']:<14} {details[:90]}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "Build me an LLM wrapper website"))
