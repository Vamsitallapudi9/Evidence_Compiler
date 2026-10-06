import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from evidence_compiler.api.deps import get_ctx
from evidence_compiler.app import AppContext
from evidence_compiler.core.models import Answer, RunEvent, RunStatus

router = APIRouter(tags=["runs"])


class RunIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class RunCreated(BaseModel):
    run_id: str


class RunSummary(BaseModel):
    id: str
    question: str
    status: RunStatus
    created_at: datetime
    error: str | None = None


class RunOut(RunSummary):
    events: list[RunEvent]
    answer: Answer | None = None
    usage: dict | None = None  # token totals + model-call log
    alive: bool = False  # a worker in this server process is executing the run


@router.post("/runs", response_model=RunCreated, status_code=201)
def create_run(body: RunIn, ctx: AppContext = Depends(get_ctx)) -> RunCreated:
    return RunCreated(run_id=ctx.runs.start(body.question.strip()))


@router.get("/runs", response_model=list[RunSummary])
def list_runs(ctx: AppContext = Depends(get_ctx)) -> list[RunSummary]:
    return [
        RunSummary(
            id=r.id, question=r.question, status=RunStatus(r.status), created_at=r.created_at
        )
        for r in ctx.repo.list_runs()
    ]


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, ctx: AppContext = Depends(get_ctx)) -> RunOut:
    row = ctx.repo.get_run(run_id)
    if row is None:
        raise HTTPException(404, "Run not found")
    return RunOut(
        id=row.id,
        question=row.question,
        status=RunStatus(row.status),
        created_at=row.created_at,
        error=row.error,
        events=ctx.runs.events(run_id),
        answer=Answer.model_validate_json(row.answer) if row.answer else None,
        usage=ctx.runs.usage(run_id),
        alive=ctx.runs.alive(run_id),
    )


@router.post("/runs/{run_id}/cancel", status_code=202)
def cancel_run(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    if ctx.repo.get_run(run_id) is None:
        raise HTTPException(404, "Run not found")
    if not ctx.runs.cancel(run_id):
        raise HTTPException(409, "Run is not in progress")
    return {"status": "cancelling"}


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, ctx: AppContext = Depends(get_ctx)) -> EventSourceResponse:
    if ctx.repo.get_run(run_id) is None:
        raise HTTPException(404, "Run not found")

    async def stream():
        sent_events = sent_calls = 0
        last_beat = 0.0
        loop = asyncio.get_running_loop()
        while True:
            events = ctx.runs.events(run_id)
            for e in events[sent_events:]:
                yield {"event": "progress", "data": e.model_dump_json()}
            sent_events = len(events)
            calls = ctx.runs.call_snapshots(run_id)
            for c in calls[sent_calls:]:
                yield {"event": "llm", "data": json.dumps(c, default=str)}
            sent_calls = len(calls)
            status = ctx.runs.status(run_id)
            finished = status in (RunStatus.DONE, RunStatus.FAILED, RunStatus.CANCELLED)
            if finished or loop.time() - last_beat >= 2:
                beat = ctx.runs.heartbeat(run_id)
                if beat is not None:
                    yield {"event": "heartbeat", "data": json.dumps(beat, default=str)}
                last_beat = loop.time()
            if finished:
                for e in ctx.runs.events(run_id)[sent_events:]:
                    yield {"event": "progress", "data": e.model_dump_json()}
                yield {"event": "done", "data": json.dumps({"status": status.value})}
                return
            await asyncio.sleep(0.3)

    return EventSourceResponse(stream())
