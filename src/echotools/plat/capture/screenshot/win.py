from __future__ import annotations

"""Windows screenshot entry (DXGI with GDI fallback)."""

from echotools.plat.capture.screenshot.config import ScreenshotConfig
from echotools.plat.capture.screenshot.win_dxgi import dxgi_run_session
from echotools.plat.capture.screenshot.win_gdi import gdi_run_session, win_draw_cursor


def win_capture_session(cfg: ScreenshotConfig) -> None:
    try:
        dxgi_run_session(cfg, win_draw_cursor)
        return
    except Exception as exc:
        print(f"[!] DXGI 失败: {exc}\n    => 回退到 GDI BitBlt")
    try:
        gdi_run_session(cfg)
    except Exception as exc:
        raise RuntimeError(f"Windows 所有截图方案均失败: {exc}") from exc
