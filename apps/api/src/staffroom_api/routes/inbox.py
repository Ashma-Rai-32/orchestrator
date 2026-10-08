"""The admin's inbox: questions employees asked (paused runs), and answering them."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    status: str
    created_at: datetime


class Answer(BaseModel):
    # For credentials this is the secret value: it goes to the secret store only.
    answer: str = Field(min_length=1, max_length=8000)


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
    """Record the answer; when the run has no open questions left, resume it once."""
    async with tenant_transaction(request.app.state.db, tenant_id) as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        item = await session.get(InboxItem, item_id)  # RLS: other tenants' items -> None
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found.")
        # Lock the run: answers to two questions of one run arriving together must not
        # both see "another question still open" and leave the run waiting forever.
        run = await session.get(Run, item.run_id, with_for_update=True)
        await session.refresh(item)
        if item.status != "open" or run is None or run.status != "waiting":
            raise HTTPException(status.HTTP_409_CONFLICT, "This question was already answered.")

        if item.secret_name:
            store = request.app.state.secrets
            if store is None:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Secret store not set up.")
            # The value goes to OpenBao only (ADR-0009); this table and the employee get
            # the name. If the commit below fails, a retry simply overwrites the value.
            await store.put(tenant_id, item.secret_name, body.answer)
            recorded = (
                f"Stored securely as {item.secret_name}. Your commands can read it from the "
                f"environment variable {item.secret_name}."
            )
        else:
            recorded = body.answer
        item.status, item.answer, item.answered_at = "answered", recorded, datetime.now(UTC)
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
        status=item.status,
        created_at=item.created_at,
    )
