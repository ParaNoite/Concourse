"""FastAPI 应用入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.db import init_db
from backend.repository import (
    accept_staged,
    create_staged,
    dismiss_staged,
    get_session,
    list_events,
    list_staged,
)
from shared.config import secrets
from shared.models import Event, StagedEvent, SubmissionPolicy

bearer = HTTPBearer(auto_error=False)


def _require_agent_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
) -> None:
    if not secrets.agent_token:
        raise HTTPException(503, "AGENT_TOKEN not configured")
    if credentials is None or credentials.credentials != secrets.agent_token:
        raise HTTPException(401, "Invalid or missing agent token")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await init_db()
    from backend.scheduler import start_scheduler, stop_scheduler
    sched = start_scheduler()
    sched.start()
    yield
    await stop_scheduler()


app = FastAPI(title="Concourse", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Session = Annotated[AsyncSession, Depends(get_session)]


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
@app.get("/events", response_model=list[Event])
async def get_events(
    session: Session,
    platforms: str | None = None,      # comma-separated
    status: str | None = None,
    end_after: datetime | None = None,
    end_before: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
):
    platform_list = [p.strip() for p in platforms.split(",")] if platforms else None
    return await list_events(
        session,
        platforms=platform_list,
        status=status,
        end_after=end_after,
        end_before=end_before,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Staged (暂存区)
# ---------------------------------------------------------------------------
@app.get("/staged", response_model=list[StagedEvent])
async def get_staged(session: Session):
    return await list_staged(session)


@app.post("/staged/{staged_id}/accept", response_model=Event)
async def accept_staged_event(staged_id: int, session: Session):
    event = await accept_staged(session, staged_id)
    if event is None:
        raise HTTPException(404, "Staged event not found")
    return event


@app.delete("/staged/{staged_id}", status_code=204)
async def dismiss_staged_event(staged_id: int, session: Session):
    ok = await dismiss_staged(session, staged_id)
    if not ok:
        raise HTTPException(404, "Staged event not found")


# ---------------------------------------------------------------------------
# Agent endpoint
# ---------------------------------------------------------------------------
class AgentRequest(Exception):
    pass


from pydantic import BaseModel


class AgentQuery(BaseModel):
    message: str


class AgentResponse(BaseModel):
    reply: str
    staged_ids: list[int] = []


@app.post("/agent", response_model=AgentResponse, dependencies=[Depends(_require_agent_token)])
async def agent(body: AgentQuery, session: Session):
    from backend.services.agent import handle_agent_message
    return await handle_agent_message(body.message, session)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "utc": datetime.now(timezone.utc).isoformat()}
