"""Fetcher 契约：所有平台 fetcher 实现同一个接口。

backend 通过 importlib 动态发现 fetchers/ 下所有模块，调用 fetch()。
新增平台 = 丢一个文件 + 在 config 注册。
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from shared.models import ScheduleEventCreate


@runtime_checkable
class Fetcher(Protocol):
    name: str

    async def fetch(self, since: datetime | None = None) -> list[ScheduleEventCreate]:
        """抓取该平台的全部事项。

        since 可选：仅返回该时间之后有变化的事项（增量）。fetcher 可以忽略
        此参数返回全量，由 repository 通过 content_hash 去重。
        """
        ...
