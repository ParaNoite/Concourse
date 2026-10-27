"""Concourse CLI — 人机均可纯键盘操作。

用法：
  concourse list                        列出所有未到期事项
  concourse list --platform scholat     按平台筛选
  concourse add "明天下午三点开组会 1小时"  自然语言添加（进暂存区）
  concourse add --title "提交报告" --end 1028+   简写语法
  concourse staged                      查看暂存区
  concourse accept 3                    接受暂存 ID=3
  concourse dismiss 3                   驳回暂存 ID=3
  concourse fetch scholat               手动触发 fetcher
  concourse creds set scholat           交互式保存凭据
  concourse creds forget scholat        删除凭据

时间简写：
  1028+  →  2026-10-28 23:59 CST（当天截止）
  1028-  →  2026-10-28 00:00 CST（当天开始）
  不带符号的 mmdd 不允许，避免歧义。
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import sys
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))


# ---------------------------------------------------------------------------
# 时间简写解析
# ---------------------------------------------------------------------------
def parse_shorthand(s: str) -> datetime:
    """
    1028+  →  当年 10月28日 23:59 CST → UTC
    1028-  →  当年 10月28日 00:00 CST → UTC
    或完整 ISO 8601 字符串。
    """
    s = s.strip()
    if s.endswith("+") or s.endswith("-"):
        sign = s[-1]
        digits = s[:-1]
        if len(digits) != 4 or not digits.isdigit():
            raise argparse.ArgumentTypeError(
                f"时间简写格式错误: {s!r}  应为 mmdd+ 或 mmdd-"
            )
        month, day = int(digits[:2]), int(digits[2:])
        year = datetime.now(CST).year
        if sign == "+":
            naive = datetime(year, month, day, 23, 59, 0)
        else:
            naive = datetime(year, month, day, 0, 0, 0)
        return naive.replace(tzinfo=CST).astimezone(timezone.utc)
    # 尝试 ISO 解析
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"无法解析时间: {s!r}")


# ---------------------------------------------------------------------------
# 子命令处理
# ---------------------------------------------------------------------------
async def _cmd_list(args: argparse.Namespace) -> None:
    from backend.db import init_db, SessionLocal
    from backend.repository import list_events

    await init_db()
    async with SessionLocal() as session:
        events = await list_events(
            session,
            platforms=[args.platform] if args.platform else None,
            status=args.status or None,
            limit=args.limit,
        )
    if not events:
        print("（暂无事项）")
        return
    for e in events:
        end = e.end_at.isoformat()[:16] if e.end_at else "     -     "
        print(f"[{e.id:>4}] {e.platform:<12} {end}  {e.status:<10} {e.title}")


async def _cmd_staged(args: argparse.Namespace) -> None:
    from backend.db import init_db, SessionLocal
    from backend.repository import list_staged

    await init_db()
    async with SessionLocal() as session:
        items = await list_staged(session)
    if not items:
        print("（暂存区为空）")
        return
    for s in items:
        end = s.end_at.isoformat()[:16] if s.end_at else "     -     "
        print(f"[{s.id:>4}] {end}  {s.proposed_by:<8} {s.title}")


async def _cmd_accept(args: argparse.Namespace) -> None:
    from backend.db import init_db, SessionLocal
    from backend.repository import accept_staged

    await init_db()
    async with SessionLocal() as session:
        event = await accept_staged(session, args.id)
    if event is None:
        print(f"未找到暂存 ID={args.id}")
        sys.exit(1)
    print(f"已接受 → events[{event.id}]: {event.title}")


async def _cmd_dismiss(args: argparse.Namespace) -> None:
    from backend.db import init_db, SessionLocal
    from backend.repository import dismiss_staged

    await init_db()
    async with SessionLocal() as session:
        ok = await dismiss_staged(session, args.id)
    print(f"已驳回 {args.id}" if ok else f"未找到暂存 ID={args.id}")


async def _cmd_add(args: argparse.Namespace) -> None:
    from backend.db import init_db, SessionLocal
    from backend.repository import create_staged

    # 自然语言模式：送 LLM 解析
    if args.message:
        await _add_via_llm(args.message)
        return

    if not args.title or not args.end:
        print("--title 和 --end 均为必填（或提供自然语言描述）", file=sys.stderr)
        sys.exit(1)

    end_at = parse_shorthand(args.end)
    start_at = parse_shorthand(args.start) if args.start else None

    await init_db()
    async with SessionLocal() as session:
        staged = await create_staged(
            session,
            title=args.title,
            end_at=end_at,
            start_at=start_at,
            description=args.description or "",
            proposed_by="cli",
        )
    print(f"已加入暂存区 [{staged.id}]: {staged.title}  截止 {end_at.isoformat()[:16]} UTC")


async def _add_via_llm(message: str) -> None:
    """自然语言 → LLM 解析 → staged event。"""
    from shared.config import agent_allowed_actions, agent_model, secrets
    import anthropic

    if not secrets.anthropic_api_key:
        print("ANTHROPIC_API_KEY 未配置，无法使用自然语言添加。", file=sys.stderr)
        sys.exit(1)

    client = anthropic.AsyncAnthropic(api_key=secrets.anthropic_api_key)
    resp = await client.messages.create(
        model=agent_model(),
        max_tokens=512,
        system=(
            "你是日程助手。用户描述一个事项，你提取标题、截止时间（ISO 8601 UTC）和开始时间（如有）。"
            '仅返回 JSON，格式：{"title":"...","end_at":"...","start_at":"...或null","description":"..."}'
            f"当前 UTC 时间：{datetime.now(timezone.utc).isoformat()}"
        ),
        messages=[{"role": "user", "content": message}],
    )
    raw = resp.content[0].text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"LLM 返回无法解析的 JSON:\n{raw}", file=sys.stderr)
        sys.exit(1)

    end_at = datetime.fromisoformat(data["end_at"]) if data.get("end_at") else None
    start_at = datetime.fromisoformat(data["start_at"]) if data.get("start_at") else None

    print(f"解析结果：{data['title']}  截止 {data.get('end_at', '-')}")
    confirm = input("加入暂存区？[Y/n]: ").strip().lower()
    if confirm in ("n", "no", "否"):
        print("已取消")
        return

    from backend.db import init_db, SessionLocal
    from backend.repository import create_staged

    await init_db()
    async with SessionLocal() as session:
        staged = await create_staged(
            session,
            title=data["title"],
            end_at=end_at,
            start_at=start_at,
            description=data.get("description", ""),
            proposed_by="cli",
        )
    print(f"已加入暂存区 [{staged.id}]")


async def _cmd_fetch(args: argparse.Namespace) -> None:
    from backend.scheduler import run_fetcher
    await run_fetcher(args.platform)


async def _cmd_creds(args: argparse.Namespace) -> None:
    from shared import credentials

    if args.creds_cmd == "set":
        u = input(f"{args.platform} 用户名/邮箱: ").strip()
        p = getpass.getpass("密码（不回显）: ")
        path = credentials.save(args.platform, {"username": u, "password": p})
        print(f"已加密保存：{path}")
    elif args.creds_cmd == "forget":
        ok = credentials.forget(args.platform)
        print("已删除" if ok else "未找到凭据")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="concourse", description="Concourse CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    # list
    ls = sub.add_parser("list", help="列出事项")
    ls.add_argument("--platform", "-p")
    ls.add_argument("--status", "-s")
    ls.add_argument("--limit", type=int, default=50)
    ls.add_argument("--json", dest="as_json", action="store_true")

    # staged
    sub.add_parser("staged", help="查看暂存区")

    # accept / dismiss
    acc = sub.add_parser("accept", help="接受暂存事项")
    acc.add_argument("id", type=int)
    dis = sub.add_parser("dismiss", help="驳回暂存事项")
    dis.add_argument("id", type=int)

    # add
    add = sub.add_parser("add", help="添加事项（进暂存区）")
    add.add_argument("message", nargs="?", help="自然语言描述")
    add.add_argument("--title", "-t")
    add.add_argument("--end", "-e", help="截止时间，支持 mmdd+ / mmdd- / ISO 8601")
    add.add_argument("--start")
    add.add_argument("--description", "-d", default="")

    # fetch
    fetch = sub.add_parser("fetch", help="手动触发 fetcher")
    fetch.add_argument("platform")

    # creds
    creds = sub.add_parser("creds", help="凭据管理")
    creds_sub = creds.add_subparsers(dest="creds_cmd", required=True)
    for action in ("set", "forget"):
        cp = creds_sub.add_parser(action)
        cp.add_argument("platform")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "list": _cmd_list,
        "staged": _cmd_staged,
        "accept": _cmd_accept,
        "dismiss": _cmd_dismiss,
        "add": _cmd_add,
        "fetch": _cmd_fetch,
        "creds": _cmd_creds,
    }
    asyncio.run(dispatch[args.cmd](args))


if __name__ == "__main__":
    main()
