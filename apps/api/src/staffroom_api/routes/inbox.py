"""The admin's inbox: questions employees asked (paused runs), and answering them."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from staffroom_api.agents.deploy import APPROVE
from staffroom_api.db.models import InboxItem, Run
from staffroom_api.db.tenancy import tenant_transaction
from staffroom_api.deps import TenantId, TenantSession
from staffroom_api.worker import run_segment

router = APIRouter(tags=["inbox"])


class InboxItemOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    employee: str
    question: str
    secret_name: str | None  # a credential: the office shows a password field
    kind: str  # question | approval
    preview_url: str | None  # approval: the private preview to review
    status: str
    created_at: datetime


class Answer(BaseModel):
    # For credentials this is the secret value: it goes to the secret store only.
    answer: str = Field(min_length=1, max_length=8000)


class Decision(BaseModel):
    approve: bool
    feedback: str | None = Field(default=None, max_length=2000)  # why, when rejecting


class AnswerResult(BaseModel):
    item: InboxItemOut
    run_resumed: bool  # false while other questions of the same run are still open


@router.get("/inbox")
async def list_open_questions(session: TenantSession) -> list[InboxItemOut]:
    rows = await session.scalars(
        select(InboxItem).where(InboxItem.status == "open").order_by(InboxItem.created_at)
    )
    return [_out(item) for item in rows]


@router.post("/inbox/{item_id}/answer")
async def answer_question(
    item_id: uuid.UUID, body: Answer, tenant_id: TenantId, request: Request
) -> AnswerResult:
    """Answer a question (or provide a secret). Approvals use /decision instead."""

    async def record(item: InboxItem) -> str:
        if item.kind != "question":
            raise HTTPException(status.HTTP_409_CONFLICT, "Use /decision for approvals.")
        if not item.secret_name:
            return body.answer
        store = request.app.state.secrets
        if store is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Secret store not set up.")
        # The value goes to OpenBao only (ADR-0009); this table and the employee get the
        # name. If the commit fails afterwards, a retry simply overwrites the value.
        await store.put(tenant_id, item.secret_name, body.answer)
        return (
            f"Stored securely as {item.secret_name}. Your commands can read it from the "
            f"environment variable {item.secret_name}."
        )

    return await _settle(item_id, tenant_id, request, record)


@router.post("/inbox/{item_id}/decision")
async def decide(
    item_id: uuid.UUID, body: Decision, tenant_id: TenantId, request: Request
) -> AnswerResult:
    """Approve or reject a request such as publishing the website (nothing is public before)."""

    async def record(item: InboxItem) -> str:
        if item.kind != "approval":
            raise HTTPException(status.HTTP_409_CONFLICT, "Use /answer for questions.")
        if body.approve:
            return APPROVE
        return f"Rejected by the admin. Feedback: {body.feedback or 'none given'}"

    return await _settle(item_id, tenant_id, request, record)


async def _settle(
    item_id: uuid.UUID,
    tenant_id: uuid.UUID,
    request: Request,
    record: Callable[[InboxItem], Awaitable[str]],
) -> AnswerResult:
    """Record one reply; once the run has nothing open left, resume it exactly once."""
    async with tenant_transaction(request.app.state.db, tenant_id) as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        item = await session.get(InboxItem, item_id)  # RLS: other tenants' items -> None
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found.")
        # Lock the run: replies to two items of one run arriving together must not both
        # see "another item still open" and leave the run waiting forever.
        run = await session.get(Run, item.run_id, with_for_update=True)
        await session.refresh(item)
        if item.status != "open" or run is None or run.status != "waiting":
            raise HTTPException(status.HTTP_409_CONFLICT, "This was already answered.")

        item.answer = await record(item)
        item.status, item.answered_at = "answered", datetime.now(UTC)
        await session.flush()

        still_open = await session.scalar(
            select(InboxItem.id).where(InboxItem.run_id == run.id, InboxItem.status == "open")
        )
        answers: dict[str, str] = {}
        if still_open is None:
            ready = await session.scalars(
                select(InboxItem).where(InboxItem.run_id == run.id, InboxItem.status == "answered")
            )
            for answered in ready:
                answers[answered.question_id] = answered.answer or ""
                answered.status = "resumed"  # never re-sent on a later pause of this run
            run.status = "queued"
        await session.flush()

    if answers:
        # After commit, so the worker sees the answers and the queued status.
        await run_segment.kiq(str(tenant_id), str(run.id), answers)
    return AnswerResult(item=_out(item), run_resumed=bool(answers))


def _out(item: InboxItem) -> InboxItemOut:
    return InboxItemOut(
        id=item.id,
        run_id=item.run_id,
        employee=item.employee,
        question=item.question,
        secret_name=item.secret_name,
        kind=item.kind,
        preview_url=item.preview_url,
        status=item.status,
        created_at=item.created_at,
    )
