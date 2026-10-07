# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "langgraph==1.2.14",
#     "langgraph-checkpoint-postgres==3.1.2",
#     "psycopg[binary]==3.3.6",
# ]
# ///
"""Spike: pause for the admin, survive the process exiting, resume later.

Question: can an employee that is blocked (needs an API key) pause, have its
state saved in Postgres, and be resumed by a DIFFERENT process with the
admin's answer? This is how agents keep working while the admin is logged out.

Setup (once):  docker compose exec postgres createdb -U staffroom spikes
Run, as separate processes:
    uv run spikes/checkpoint-interrupt/main.py start
    uv run spikes/checkpoint-interrupt/main.py resume <thread_id> OPENAI_KEY_ACME
    uv run spikes/checkpoint-interrupt/main.py history <thread_id>
"""

import operator
import os
import sys
import uuid
from typing import Annotated, TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

DB_URL = os.environ.get("SPIKE_DB_URL", "postgresql://staffroom:staffroom@localhost:5432/spikes")


class State(TypedDict):
    goal: str
    log: Annotated[list[str], operator.add]


class AdminAnswer(BaseModel):
    """What the admin's inbox form sends back. A secret NAME, never the secret itself."""

    secret_name: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$", description="Name of the stored key")


def plan(state: State) -> dict:
    print("  (node) plan: running")
    return {"log": ["coordinator: planned the site"]}


def build_backend(state: State) -> dict:
    # Everything above interrupt() RE-RUNS on resume. Keep it side-effect free.
    print("  (node) build_backend: running from the top")
    answer: AdminAnswer = interrupt(
        {
            "employee": "Ada",
            "message": "I need an API key for the LLM provider to build the chat feature.",
        },
        response_schema=AdminAnswer,
    )
    print(f"  (node) build_backend: got {answer!r}")
    return {"log": [f"Ada: built backend using secret '{answer.secret_name}'"]}


def deploy(state: State) -> dict:
    print("  (node) deploy: running")
    return {"log": ["deploy: ready for admin approval"]}


def build_graph(checkpointer: PostgresSaver):  # type: ignore[no-untyped-def]
    builder = StateGraph(State)
    builder.add_node("plan", plan)
    builder.add_node("build_backend", build_backend)
    builder.add_node("deploy", deploy)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "build_backend")
    builder.add_edge("build_backend", "deploy")
    builder.add_edge("deploy", END)
    return builder.compile(checkpointer=checkpointer)


def run(graph, payload, thread_id: str) -> None:  # type: ignore[no-untyped-def]
    config = {"configurable": {"thread_id": thread_id}}
    for part in graph.stream(payload, config, stream_mode="updates", version="v2"):
        data = part["data"]
        if "__interrupt__" in data:
            intr = data["__interrupt__"][0]
            print("\n  >> PAUSED. Inbox item for the admin:")
            print(f"     {intr.value}")
            print(f"     form schema: {intr.response_schema}")
        else:
            print(f"  update: {data}")
    snapshot = graph.get_state(config)
    print(f"\n  next node(s): {snapshot.next or 'none, finished'}")
    print(f"  log so far:   {snapshot.values.get('log')}")


def main() -> None:
    cmd, *args = sys.argv[1:] or ["start"]
    with PostgresSaver.from_conn_string(DB_URL) as checkpointer:
        checkpointer.setup()  # creates checkpoint tables if missing (idempotent)
        graph = build_graph(checkpointer)

        if cmd == "start":
            # Tenant-prefixed thread id: checkpoint tables have no tenant column.
            thread_id = f"tenant-a:{uuid.uuid4()}"
            print(f"== start, thread {thread_id} (pid {os.getpid()}) ==")
            run(graph, {"goal": "LLM wrapper website", "log": []}, thread_id)
            print(f"\n  process exits now. Resume later with:\n  uv run {sys.argv[0]} resume {thread_id} OPENAI_KEY_ACME")

        elif cmd == "resume":
            thread_id, secret_name = args
            print(f"== resume, thread {thread_id} (pid {os.getpid()}, a new process) ==")
            run(graph, Command(resume={"secret_name": secret_name}), thread_id)

        elif cmd == "history":
            (thread_id,) = args
            print(f"== checkpoints for {thread_id}, newest first ==")
            for snap in graph.get_state_history({"configurable": {"thread_id": thread_id}}):
                step = snap.metadata.get("step") if snap.metadata else "?"
                print(f"  step {step}: next={snap.next}  log entries={len(snap.values.get('log', []))}")


if __name__ == "__main__":
    main()
