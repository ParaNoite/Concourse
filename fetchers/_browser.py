"""Shared Playwright browser utilities for all Playwright-based fetchers."""
from __future__ import annotations

from pathlib import Path

BROWSER_DATA_ROOT = Path(__file__).resolve().parent.parent / ".browser-data"


async def launch_context(pw, platform: str, headless: bool = True):
    """Launch a persistent browser context for the given platform.

    Tries msedge → chrome → chromium → bundled-chromium in order.
    Session data is stored under .browser-data/<platform>/ so login state
    persists between runs.
    """
    data_dir = BROWSER_DATA_ROOT / platform
    data_dir.mkdir(parents=True, exist_ok=True)
    for channel in ("msedge", "chrome", "chromium", None):
        kwargs = {"channel": channel} if channel else {}
        try:
            ctx = await pw.chromium.launch_persistent_context(
                user_data_dir=str(data_dir),
                headless=headless,
                accept_downloads=False,
                **kwargs,
            )
            return ctx
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError(
        f"无法为 {platform} 启动浏览器（msedge / chrome / chromium 均失败）。"
        "请确认已安装 Playwright 浏览器：uv run playwright install chromium"
    )
