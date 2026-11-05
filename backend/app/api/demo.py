"""Local demo commands and replayable Server-Sent Events."""

from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from app.demo.scenarios import SCENARIOS

router = APIRouter(prefix="/api/demo", tags=["demo"])


class StartDemo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["non_disruptive", "disruptive"]


@router.get("/scenarios")
async def scenarios():
    return SCENARIOS


@router.post("/run", status_code=202)
async def start_demo(body: StartDemo, request: Request):
    try:
        run = request.app.state.demo_store.start(body.scenario)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return {"demoId": run.demo_id, "resourceKey": run.resource_key,
            "eventsUrl": f"/api/demo/events/{run.demo_id}"}


@router.get("/events/{demo_id}")
async def events(demo_id: str, request: Request,
                 last_event_id: str | None = Header(default=None)):
    store = request.app.state.demo_store
    store.prune()
    run = store.runs.get(demo_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Demo not found or expired. Start a new run.")
    try:
        after = int(last_event_id or 0)
        if after < 0 or after > len(run.events):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Last-Event-ID.") from exc
    return StreamingResponse(run.stream(after), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
    })
