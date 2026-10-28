"""Agent service — LLM 驱动的日程操作。

白名单 action 在 config.yaml agent.allowed_actions 里配置。
写操作只产 staged_event 提案，不直接写 events。
"""

from __future__ import annotations

import json

import anthropic
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.repository import create_staged, list_events
from shared.config import agent_allowed_actions, agent_model, secrets
from shared.models import SubmissionPolicy

_TOOLS = [
    {
        "name": "read_events",
        "description": "返回数据库中的日程/作业事项列表，可按平台、状态、截止时间过滤。",
        "input_schema": {
            "type": "object",
            "properties": {
                "platforms": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "string"},
                "days_ahead": {"type": "integer", "description": "未来 N 天内到期的事项"},
            },
        },
    },
    {
        "name": "summarize",
        "description": "对日程列表做自然语言汇总，不修改任何数据。",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
    {
        "name": "find_conflicts",
        "description": "查找时间段重叠的事项。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "draft_add_event",
        "description": "将一个新事项提案写入暂存区，等待人工确认后才生效。",
        "input_schema": {
            "type": "object",
            "required": ["title", "end_at"],
            "properties": {
                "title": {"type": "string"},
                "end_at": {"type": "string", "description": "ISO 8601 UTC"},
                "start_at": {"type": "string", "description": "ISO 8601 UTC，可选"},
                "description": {"type": "string"},
                "platform": {"type": "string", "description": "平台标识，如 scholat / codeforces / manual"},
                "course": {"type": "string", "description": "平台内课程/子分类，如 'Java程序设计'"},
            },
        },
    },
]


async def handle_agent_message(message: str, session: AsyncSession) -> dict:
    allowed = agent_allowed_actions()
    available_tools = [t for t in _TOOLS if t["name"] in allowed]

    client = anthropic.AsyncAnthropic(api_key=secrets.anthropic_api_key)
    messages = [{"role": "user", "content": message}]
    staged_ids: list[int] = []

    while True:
        resp = await client.messages.create(
            model=agent_model(),
            max_tokens=2048,
            tools=available_tools,  # type: ignore[arg-type]
            messages=messages,
        )

        if resp.stop_reason == "end_turn":
            reply = " ".join(
                b.text for b in resp.content if hasattr(b, "text")
            )
            return {"reply": reply, "staged_ids": staged_ids}

        if resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                name = block.name
                if name not in allowed:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "该操作不在允许列表中，已拒绝。",
                    })
                    continue
                result = await _dispatch(name, block.input, session, staged_ids)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return {"reply": "Agent 返回了意外的停止原因。", "staged_ids": staged_ids}


async def _dispatch(
    name: str,
    args: dict,
    session: AsyncSession,
    staged_ids: list[int],
) -> object:
    from datetime import timedelta, timezone

    if name == "read_events":
        from datetime import datetime
        days = args.get("days_ahead")
        end_before = (
            datetime.now(timezone.utc) + timedelta(days=days) if days else None
        )
        events = await list_events(
            session,
            platforms=args.get("platforms"),
            status=args.get("status"),
            end_before=end_before,
        )
        return [
            {
                "id": e.id,
                "platform": e.platform,
                "title": e.title,
                "status": e.status,
                "end_at": e.end_at.isoformat() if e.end_at else None,
                "submission_policy": e.submission_policy,
            }
            for e in events
        ]

    if name == "draft_add_event":
        from datetime import datetime
        end_at = datetime.fromisoformat(args["end_at"]) if args.get("end_at") else None
        start_at = datetime.fromisoformat(args["start_at"]) if args.get("start_at") else None
        staged = await create_staged(
            session,
            title=args["title"],
            end_at=end_at,
            start_at=start_at,
            platform=args.get("platform", "manual"),
            course=args.get("course", ""),
            description=args.get("description", ""),
            proposed_by="agent",
        )
        staged_ids.append(staged.id)
        return {"staged_id": staged.id, "title": staged.title, "end_at": args.get("end_at")}

    if name in ("summarize", "find_conflicts"):
        # 这两个 action 不需要额外工具调用，LLM 自己基于 read_events 的结果完成
        return {}

    return {"error": f"unknown action: {name}"}
