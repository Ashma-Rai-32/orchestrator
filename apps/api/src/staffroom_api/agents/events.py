"""Domain events a run emits. Stored per tenant and streamed to the office UI.

Framework-neutral on purpose: the UI and database never see LangGraph types.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter


class RunStarted(BaseModel):
    type: Literal["run_started"] = "run_started"
    goal: str


class RunResumed(BaseModel):
    """A worker picked the run up again from its last checkpoint (e.g. after a crash)."""

    type: Literal["run_resumed"] = "run_resumed"
    from_step: str


class TaskAssigned(BaseModel):
    type: Literal["task_assigned"] = "task_assigned"
    employee: str
    task: str


class TaskFinished(BaseModel):
    type: Literal["task_finished"] = "task_finished"
    employee: str
    result: str


class TaskFailed(BaseModel):
    """An employee could not finish; the run continues and the coordinator is told."""

    type: Literal["task_failed"] = "task_failed"
    employee: str
    error: str  # exception type only: messages may contain secrets


class RunFinished(BaseModel):
    type: Literal["run_finished"] = "run_finished"
    summary: str


class RunFailed(BaseModel):
    type: Literal["run_failed"] = "run_failed"
    error: str


TeamEvent = Annotated[
    RunStarted | RunResumed | TaskAssigned | TaskFinished | TaskFailed | RunFinished | RunFailed,
    Field(discriminator="type"),
]
team_event = TypeAdapter[TeamEvent](TeamEvent)
