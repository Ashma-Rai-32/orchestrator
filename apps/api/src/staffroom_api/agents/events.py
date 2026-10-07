"""Domain events a run emits. Stored per tenant and streamed to the office UI.

Framework-neutral on purpose: the UI and database never see LangGraph types.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter


class RunStarted(BaseModel):
    type: Literal["run_started"] = "run_started"
    goal: str


class TaskAssigned(BaseModel):
    type: Literal["task_assigned"] = "task_assigned"
    employee: str
    task: str


class TaskFinished(BaseModel):
    type: Literal["task_finished"] = "task_finished"
    employee: str
    result: str


class RunFinished(BaseModel):
    type: Literal["run_finished"] = "run_finished"
    summary: str


class RunFailed(BaseModel):
    type: Literal["run_failed"] = "run_failed"
    error: str


TeamEvent = Annotated[
    RunStarted | TaskAssigned | TaskFinished | RunFinished | RunFailed,
    Field(discriminator="type"),
]
team_event = TypeAdapter[TeamEvent](TeamEvent)
