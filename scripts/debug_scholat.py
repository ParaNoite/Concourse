"""只读调试：抓取学者网原始页面与解析结果并落盘，不写数据库。

uv run python scripts/debug_scholat.py            # 用 config.yaml 的 course_ids
uv run python scripts/debug_scholat.py 3017 3854  # 指定课程
输出到 .debug/scholat/<时间戳>/
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bs4 import BeautifulSoup  # noqa: E402

from fetchers import scholat as s  # noqa: E402
from fetchers._browser import launch_context  # noqa: E402
from shared import config as cfg  # noqa: E402
from shared import credentials  # noqa: E402


def row_dump(list_html: str) -> list[dict]:
    """每个作业行：状态单元格原文、整行各单元格文本、整行 HTML。"""
    soup = BeautifulSoup(list_html, "html.parser")
    table = soup.find("table", id="datalist") or soup.find("table", class_="datalist")
    rows = []
    if table is None:
        return rows
    for tr in table.find_all("tr"):
        link = tr.find("a", href=re.compile(r"S_oneHomework\.html", re.I))
        if link is None:
            continue
        m = re.search(r"homeworkId=(\d+)", link.get("href", ""), re.I)
        hid = m.group(1) if m else None
        cell = tr.find("td", id=f"upload{hid}")
        rows.append({
            "homework_id": hid,
            "status_cell_found_by_id": cell is not None,
            "status_cell_text": cell.get_text(" ", strip=True) if cell else None,
            "status_cell_html": str(cell) if cell else None,
            "cells": [td.get_text(" ", strip=True) for td in tr.find_all("td")],
            "row_html": str(tr),
        })
    return rows


async def main(course_ids: list[str]) -> None:
    from playwright.async_api import async_playwright

    out = ROOT / ".debug" / "scholat" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        context = await launch_context(pw, s.NAME, headless=True)
        try:
            await s._ensure_logged_in(context, credentials.load(s.NAME), course_ids[0])
            events = []
            for cid in course_ids:
                resp = await context.request.get(
                    f"{s.BASE}/course/S_homeworkList.html?courseId={cid}", timeout=30000
                )
                html = await resp.text()
                (out / f"list_{cid}.html").write_text(html, encoding="utf-8")
                rows = row_dump(html)
                (out / f"rows_{cid}.json").write_text(
                    json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                for hw in s.parse_homework_list(html, cid):
                    d = await context.request.get(hw.url, timeout=30000)
                    dhtml = await d.text()
                    (out / f"detail_{cid}_{hw.homework_id}.html").write_text(dhtml, encoding="utf-8")
                    hw = s.parse_homework_detail(dhtml, hw)
                    ev = s._to_event(hw, cid).model_dump(mode="json")
                    ev["_status_raw"] = hw.status
                    events.append(ev)
                print(f"course {cid}: HTTP {resp.status}, {len(rows)} rows")
            (out / "events.json").write_text(
                json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        finally:
            await context.close()

    print(f"saved to {out}")
    for ev in events:
        print(f"  {ev['course']:>5} {ev['status']:<9} raw={ev['_status_raw']!r:<16} {ev['title'][:30]}")


if __name__ == "__main__":
    ids = sys.argv[1:] or cfg.fetcher_kwargs("scholat").get("course_ids") or []
    asyncio.run(main([str(i) for i in ids]))
