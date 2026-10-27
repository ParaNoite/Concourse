from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


class SubmissionPolicy(str, Enum):
    NONE = "none"
    ONCE = "once"
    LATE = "late"
    UNLIMITED = "unlimited"


class ScheduleEventCreate(BaseModel):
    """Fetchers 产出的归一化事项。Repository 负责落库并计算 content_hash。"""

    platform: str
    source_id: str
    title: str
    description: str = ""
    location: str = ""
    meeting_url: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    tz_original: str | None = None
    all_day: bool = False
    status: str = "open"
    submission_policy: SubmissionPolicy = SubmissionPolicy.NONE
    organizer_name: str | None = None
    organizer_email: str | None = None
    attendees: list[dict] = Field(default_factory=list)
    recurrence_rrule: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class Event(SQLModel, table=True):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("platform", "source_id", name="uq_platform_source"),)

    id: int | None = SQLField(default=None, primary_key=True)
    platform: str = SQLField(index=True)
    source_id: str = SQLField(index=True)
    uid: str | None = None
    title: str
    description: str = ""
    location: str = ""
    meeting_url: str | None = None
    # 库内统一存 naive UTC；读写由 repository 在边界换算。
    start_at: datetime | None = SQLField(default=None, index=True)
    end_at: datetime | None = SQLField(default=None, index=True)
    tz_original: str | None = None
    all_day: bool = False
    status: str = "open"
    submission_policy: SubmissionPolicy = SQLField(default=SubmissionPolicy.NONE)
    organizer_name: str | None = None
    organizer_email: str | None = None
    attendees: list | None = SQLField(default=None, sa_column=Column(JSON))
    recurrence_rrule: str | None = None
    content_hash: str = SQLField(index=True)
    raw_payload: dict | None = SQLField(default=None, sa_column=Column(JSON))
    first_seen_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = SQLField(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class StagedEvent(SQLModel, table=True):
    """Agent / CLI 产出的待确认条目。accept 后变成 platform='manual' 的 Event。"""

    __tablename__ = "staged_events"

    id: int | None = SQLField(default=None, primary_key=True)
    platform: str = SQLField(default="manual", index=True)
    source_id: str = SQLField(index=True)
    title: str
    description: str = ""
    start_at: datetime | None = SQLField(default=None)
    end_at: datetime | None = SQLField(default=None)
    tz_original: str | None = None
    all_day: bool = False
    status: str = "open"
    submission_policy: SubmissionPolicy = SQLField(default=SubmissionPolicy.NONE)
    proposed_by: str = SQLField(default="agent")  # agent | cli
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    raw_payload: dict | None = SQLField(default=None, sa_column=Column(JSON))


def compute_content_hash(ev: ScheduleEventCreate) -> str:
    payload = {
        "platform": ev.platform,
        "source_id": ev.source_id,
        "title": ev.title,
        "description": ev.description,
        "location": ev.location,
        "meeting_url": ev.meeting_url,
        "start_at": ev.start_at.isoformat() if ev.start_at else None,
        "end_at": ev.end_at.isoformat() if ev.end_at else None,
        "status": ev.status,
        "submission_policy": ev.submission_policy.value,
        "organizer_name": ev.organizer_name,
        "organizer_email": ev.organizer_email,
        "attendees": ev.attendees,
        "recurrence_rrule": ev.recurrence_rrule,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def to_naive_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def to_aware_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
