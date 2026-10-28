"""FastAPI 应用入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.db import init_db
from backend.repository import (
    accept_staged,
    create_staged,
    delete_event,
    dismiss_staged,
    get_session,
    list_events,
    list_fetcher_states,
    list_staged,
    list_trash,
    mark_done,
    permanent_delete_event,
    restore_event,
    update_fetcher_settings,
)
from shared.config import secrets
from shared.models import Event, FetcherState, StagedEvent, SubmissionPolicy, to_aware_utc

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
    await start_scheduler()
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


@app.delete("/events/{event_id}", status_code=204)
async def delete_event_route(event_id: int, session: Session):
    ok = await delete_event(session, event_id)
    if not ok:
        raise HTTPException(404, "Event not found")


@app.post("/events/{event_id}/done", response_model=Event)
async def mark_event_done(event_id: int, session: Session):
    event = await mark_done(session, event_id)
    if event is None:
        raise HTTPException(404, "Event not found or already deleted")
    return event


@app.post("/events/{event_id}/restore", response_model=Event)
async def restore_event_route(event_id: int, session: Session):
    event = await restore_event(session, event_id)
    if event is None:
        raise HTTPException(404, "Event not found or not in trash")
    return event


@app.delete("/events/{event_id}/permanent", status_code=204)
async def permanent_delete_route(event_id: int, session: Session):
    ok = await permanent_delete_event(session, event_id)
    if not ok:
        raise HTTPException(404, "Event not found in trash")


@app.get("/trash", response_model=list[Event])
async def get_trash(session: Session, limit: int = 200):
    return await list_trash(session, limit=limit)


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
# Fetchers（启停、频率、运行状态、立即触发）
# ---------------------------------------------------------------------------
class FetcherInfo(BaseModel):
    name: str
    enabled: bool
    cron: str
    cron_default: str
    cron_overridden: bool
    running: bool
    next_run_at: datetime | None
    config: dict
    last_trigger: str | None = None
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_success_at: datetime | None = None
    last_status: str | None = None
    last_error: str = ""
    last_count: int = 0
    last_changed: int = 0
    last_duration_ms: int = 0


class FetcherPatch(BaseModel):
    enabled: bool | None = None
    cron: str | None = None  # 显式传 null 或 "" 恢复 config.yaml 默认值


def _fetcher_info(name: str, state: FetcherState | None) -> FetcherInfo:
    from backend import scheduler as sch
    from shared import config as cfg

    enabled, cron = sch.effective(name, state)
    s = state or FetcherState(name=name)
    return FetcherInfo(
        name=name,
        enabled=enabled,
        cron=cron,
        cron_default=cfg.schedule_for(name),
        cron_overridden=bool(state and state.cron),
        running=sch.is_running(name),
        next_run_at=sch.next_run_at(name) if enabled else None,
        config=cfg.fetcher_kwargs(name),
        last_trigger=s.last_trigger,
        last_started_at=to_aware_utc(s.last_started_at),
        last_finished_at=to_aware_utc(s.last_finished_at),
        last_success_at=to_aware_utc(s.last_success_at),
        last_status=s.last_status,
        last_error=s.last_error,
        last_count=s.last_count,
        last_changed=s.last_changed,
        last_duration_ms=s.last_duration_ms,
    )


def _require_fetcher(name: str) -> None:
    from backend.scheduler import available_fetchers

    if name not in available_fetchers():
        raise HTTPException(404, f"Unknown fetcher: {name}")


@app.get("/fetchers", response_model=list[FetcherInfo])
async def get_fetchers(session: Session):
    from backend.scheduler import available_fetchers

    states = {s.name: s for s in await list_fetcher_states(session)}
    return [_fetcher_info(n, states.get(n)) for n in available_fetchers()]


@app.patch("/fetchers/{name}", response_model=FetcherInfo)
async def patch_fetcher(name: str, body: FetcherPatch, session: Session):
    from backend import scheduler as sch

    _require_fetcher(name)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("enabled") is None:
        changes.pop("enabled", None)
    if changes.get("cron"):
        changes["cron"] = changes["cron"].strip()
        try:
            sch.validate_cron(changes["cron"])
        except ValueError as exc:
            raise HTTPException(422, f"无效的 cron 表达式: {exc}") from exc
    state = await update_fetcher_settings(
        session, name, default_enabled=sch.default_enabled(name), changes=changes,
    )
    await sch.apply_settings(name)
    return _fetcher_info(name, state)


@app.post("/fetchers/{name}/run", status_code=202)
async def run_fetcher_now(name: str):
    from backend.scheduler import trigger_now

    _require_fetcher(name)
    if not trigger_now(name):
        raise HTTPException(409, "Fetcher is already running")
    return {"started": True}


# ---------------------------------------------------------------------------
# Agent endpoint
# ---------------------------------------------------------------------------
class AgentRequest(Exception):
    pass


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
