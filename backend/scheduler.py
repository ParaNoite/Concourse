"""定时调度 fetcher 并把结果 upsert 进数据库。

用 APScheduler 进程内调度；同一平台加锁防并发重抓。
启用/停用与 cron 覆盖存在 fetcher_states 表，优先于 config.yaml；
修改后通过 apply_settings() 热更新，无需重启。
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import pkgutil
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.repository import get_fetcher_state, list_fetcher_states, upsert_event
from shared import config as cfg
from shared.models import FetcherState

log = logging.getLogger("concourse.scheduler")

_scheduler: AsyncIOScheduler | None = None
_locks: dict[str, asyncio.Lock] = {}
_background: set[asyncio.Task] = set()


def _class_name(name: str) -> str:
    return "".join(p.capitalize() for p in name.split("_")) + "Fetcher"


def _load_fetcher(name: str) -> Any:
    """根据 fetcher 名加载模块并实例化。"""
    kwargs = cfg.fetcher_kwargs(name)
    module = importlib.import_module(f"fetchers.{name}")
    cls = getattr(module, _class_name(name))
    return cls(**kwargs)


def available_fetchers() -> list[str]:
    """config.yaml 中配置的 + fetchers/ 目录下存在的模块。"""
    import fetchers

    names = set(cfg.configured_fetchers())
    for mod in pkgutil.iter_modules(fetchers.__path__):
        if not mod.name.startswith("_") and mod.name != "base":
            names.add(mod.name)
    return sorted(names)


def default_enabled(name: str) -> bool:
    # 只有写进 config.yaml schedule 的才默认启用；新加的 fetcher 文件默认停用，需在界面里打开
    return name in (cfg.load_config().get("schedule") or {})


def effective(name: str, state: FetcherState | None) -> tuple[bool, str]:
    enabled = state.enabled if state is not None else default_enabled(name)
    cron = (state.cron if state is not None and state.cron else None) or cfg.schedule_for(name)
    return enabled, cron


def validate_cron(expr: str) -> None:
    CronTrigger.from_crontab(expr)


def is_running(name: str) -> bool:
    lock = _locks.get(name)
    return lock is not None and lock.locked()


def next_run_at(name: str) -> datetime | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(f"fetcher.{name}")
    return job.next_run_time if job else None


async def _fetch(fetcher: Any) -> list:
    # uvicorn --reload on Windows forces SelectorEventLoop, which cannot spawn
    # subprocesses (Playwright needs to). Run fetch() on a Proactor loop in a worker thread.
    if sys.platform == "win32" and not isinstance(
        asyncio.get_running_loop(), asyncio.ProactorEventLoop
    ):
        def _run() -> list:
            loop = asyncio.ProactorEventLoop()
            try:
                return loop.run_until_complete(fetcher.fetch())
            finally:
                loop.close()

        return await asyncio.to_thread(_run)
    return await fetcher.fetch()


async def _record(name: str, **fields: Any) -> None:
    from backend.db import SessionLocal

    async with SessionLocal() as session:
        state = await get_fetcher_state(session, name)
        if state is None:
            state = FetcherState(name=name, enabled=default_enabled(name))
        for k, v in fields.items():
            setattr(state, k, v)
        session.add(state)
        await session.commit()


async def run_fetcher(name: str, trigger: str = "schedule") -> bool:
    """运行一次 fetcher 并记录结果；已在运行则跳过并返回 False。"""
    lock = _locks.setdefault(name, asyncio.Lock())
    if lock.locked():
        log.info("fetcher %s 已在运行，跳过本次触发", name)
        return False
    async with lock:
        from backend.db import SessionLocal

        started = datetime.now(timezone.utc)
        t0 = time.monotonic()
        await _record(name, last_trigger=trigger, last_started_at=started)
        log.info("fetcher %s 开始 (%s)", name, trigger)

        count = changed = 0
        try:
            fetcher = _load_fetcher(name)
            events = await _fetch(fetcher)
            count = len(events)
            async with SessionLocal() as session:
                for ev in events:
                    _, is_changed = await upsert_event(session, ev)
                    changed += int(is_changed)
        except Exception as exc:  # noqa: BLE001
            log.exception("fetcher %s 抓取失败: %s", name, exc)
            await _record(
                name,
                last_finished_at=datetime.now(timezone.utc),
                last_status="error",
                last_error=traceback.format_exc()[-2000:],
                last_count=count,
                last_changed=changed,
                last_duration_ms=int((time.monotonic() - t0) * 1000),
            )
            return True

        finished = datetime.now(timezone.utc)
        await _record(
            name,
            last_finished_at=finished,
            last_success_at=finished,
            last_status="ok",
            last_error="",
            last_count=count,
            last_changed=changed,
            last_duration_ms=int((time.monotonic() - t0) * 1000),
        )
        log.info("fetcher %s 完成: 共 %d 条, 其中 %d 条更新", name, count, changed)
        return True


def trigger_now(name: str) -> bool:
    """后台立即运行；已在运行返回 False。"""
    if is_running(name):
        return False
    task = asyncio.create_task(run_fetcher(name, trigger="manual"))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return True


def _apply_one(name: str, enabled: bool, cron: str) -> None:
    assert _scheduler is not None
    job_id = f"fetcher.{name}"
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
    if not enabled:
        return
    try:
        trigger = CronTrigger.from_crontab(cron)
    except Exception as exc:  # noqa: BLE001
        log.warning("无法解析 cron %r (%s): %s", cron, name, exc)
        return
    _scheduler.add_job(
        run_fetcher, trigger, args=[name], id=job_id,
        max_instances=1, coalesce=True, misfire_grace_time=300,
    )


async def apply_settings(name: str | None = None) -> None:
    """按 DB 中的设置（缺省回落 config.yaml）重建一个或全部 job。"""
    if _scheduler is None:
        return
    from backend.db import SessionLocal

    async with SessionLocal() as session:
        states = {s.name: s for s in await list_fetcher_states(session)}
    names = [name] if name else available_fetchers()
    for n in names:
        _apply_one(n, *effective(n, states.get(n)))


async def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    await apply_settings()
    return _scheduler


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
