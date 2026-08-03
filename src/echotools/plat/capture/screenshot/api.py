from __future__ import annotations

"""Portable multi-frame screenshot API."""

import os
import sys

from echotools.plat.capture.screenshot.config import ScreenshotConfig
from echotools.plat.capture.shared.platform import _OS, IS_LINUX, IS_MACOS, IS_WINDOWS

if IS_WINDOWS:
    from echotools.plat.capture.screenshot.win import win_capture_session
elif IS_MACOS:
    from echotools.plat.capture.screenshot.mac import mac_capture_session
elif IS_LINUX:
    from echotools.plat.capture.screenshot.linux import linux_capture_session


def capture_screenshots(config: ScreenshotConfig | None = None) -> str:
    """Capture screenshots according to config. Returns output directory."""
    cfg = config or ScreenshotConfig()
    os.makedirs(cfg.output_dir, exist_ok=True)
    py_ver = sys.version_info
    print(
        f"[*] 平台: {_OS} | Python {py_ver.major}.{py_ver.minor} | "
        f"目标: {cfg.capture_count} 张 -> ./{cfg.output_dir}/"
    )
    if IS_WINDOWS:
        win_capture_session(cfg)
    elif IS_MACOS:
        mac_capture_session(cfg)
    elif IS_LINUX:
        linux_capture_session(cfg)
    else:
        raise RuntimeError(f"不支持的操作系统: {_OS}")
    print(f"[+] 全部完成，输出目录: ./{cfg.output_dir}/")
    return cfg.output_dir
