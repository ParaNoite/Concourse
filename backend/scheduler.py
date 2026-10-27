"""定时调度 fetcher 并把结果 upsert 进数据库。

用 APScheduler 进程内调度；同一平台加锁防并发重抓。
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.repository import upsert_event
from shared import config as cfg

log = logging.getLogger("concourse.scheduler")

_scheduler: AsyncIOScheduler | None = None
_locks: dict[str, asyncio.Lock] = {}


def _load_fetcher(name: str) -> Any:
    """根据 fetcher 名加载模块并实例化。"""
    kwargs = cfg.fetcher_kwargs(name)
    module = importlib.import_module(f"fetchers.{name}")
    cls_name = "".join(p.capitalize() for p in name.split("_")) + "Fetcher"
    cls = getattr(module, cls_name)
    return cls(**kwargs)


async def run_fetcher(name: str) -> None:
    lock = _locks.setdefault(name, asyncio.Lock())
    if lock.locked():
        log.info("fetcher %s 已在运行，跳过本次触发", name)
        return
    async with lock:
        from backend.db import SessionLocal

        log.info("fetcher %s 开始", name)
        try:
            fetcher = _load_fetcher(name)
            events = await fetcher.fetch()
        except Exception as exc:  # noqa: BLE001
            log.exception("fetcher %s 抓取失败: %s", name, exc)
            return

        changed = 0
        async with SessionLocal() as session:
            for ev in events:
                _, is_changed = await upsert_event(session, ev)
                changed += int(is_changed)
        log.info("fetcher %s 完成: 共 %d 条, 其中 %d 条更新", name, len(events), changed)


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = AsyncIOScheduler()
    for name in (cfg.load_config().get("schedule") or {}):
        expr = cfg.schedule_for(name)
        try:
            trigger = CronTrigger.from_crontab(expr)
        except Exception as exc:  # noqa: BLE001
            log.warning("无法解析 cron %r (%s): %s", expr, name, exc)
            continue
        _scheduler.add_job(run_fetcher, trigger, args=[name], id=f"fetcher.{name}")
    return _scheduler


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
