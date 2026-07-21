from __future__ import annotations

"""进程与端口管理工具（跨平台）。"""

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import List, Set

from echotools.base.logger.manager import get_logger

__all__ = ["PortReleaseResult", "ensure_port_available"]

logger = get_logger(__name__)


@dataclass
class PortReleaseResult:
    """端口释放结果。"""

    port: int
    occupied: bool
    released: bool
    pids: List[int]
    detail: str


def ensure_port_available(
    port: int, force_kill: bool
) -> PortReleaseResult:
    """确保目标端口可用。

    Args:
        port: 目标端口。
        force_kill: 占用时是否强制终止。

    Returns:
        端口处理结果。
    """
    pids = sorted(_find_pids_by_port(port))
    if not pids:
        return PortReleaseResult(port, False, True, [], "port is free")
    if not force_kill:
        return PortReleaseResult(
            port, True, False, pids, "port occupied, force kill disabled"
        )
    released: List[int] = []
    for pid in pids:
        if _kill_pid(pid):
            released.append(pid)
    # Retry with delay: OS may need a moment to release the TCP socket
    # after the process is killed (especially on Windows).
    max_retries = 3
    for attempt in range(max_retries + 1):
        remaining = sorted(_find_pids_by_port(port))
        if not remaining:
            return PortReleaseResult(
                port, True, True, released, "force killed processes"
            )
        if attempt < max_retries:
            time.sleep(0.5)
    return PortReleaseResult(
        port, True, False, remaining, "failed to release all"
    )


def _find_pids_by_port(port: int) -> Set[int]:
    """查找监听端口的进程。"""
    if sys.platform == "win32":
        return _find_pids_windows(port)
    return _find_pids_unix(port)


def _find_pids_unix(port: int) -> Set[int]:
    """类 Unix 平台查找。"""
    pids: Set[int] = set()
    candidates = [
        ["lsof", "-ti", "tcp:{}".format(port)],
        ["fuser", "-n", "tcp", str(port)],
    ]
    for command in candidates:
        try:
            result = subprocess.run(
                command, check=False, capture_output=True, text=True
            )
        except OSError:
            continue
        pids.update(_parse_int_tokens(result.stdout))
        pids.update(_parse_int_tokens(result.stderr))
    if pids:
        return pids
    try:
        result = subprocess.run(
            ["ss", "-ltnp", "sport", "=", ":{}".format(port)],
            check=False,
            capture_output=True,
            text=True,
        )
        pids.update(_parse_ss_output(result.stdout))
    except OSError:
        return pids
    return pids


def _find_pids_windows(port: int) -> Set[int]:
    """Windows 平台查找。"""
    pids: Set[int] = set()
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        return pids
    marker = ":{}".format(port)
    for line in result.stdout.splitlines():
        normalized = " ".join(line.split())
        if marker not in normalized or "LISTENING" not in normalized:
            continue
        parts = normalized.split(" ")
        if not parts:
            continue
        try:
            pids.add(int(parts[-1]))
        except ValueError:
            continue
    return pids


def _parse_int_tokens(text: str) -> Set[int]:
    """从文本提取整数。"""
    result: Set[int] = set()
    for token in text.replace("\n", " ").split(" "):
        token = token.strip()
        if not token:
            continue
        try:
            result.add(int(token))
        except ValueError:
            continue
    return result


def _parse_ss_output(text: str) -> Set[int]:
    """解析 ss 输出 pid。"""
    result: Set[int] = set()
    marker = "pid="
    for line in text.splitlines():
        start = 0
        while True:
            idx = line.find(marker, start)
            if idx == -1:
                break
            idx += len(marker)
            digits: List[str] = []
            while idx < len(line) and line[idx].isdigit():
                digits.append(line[idx])
                idx += 1
            if digits:
                result.add(int("".join(digits)))
            start = idx
    return result


def _kill_pid(pid: int) -> bool:
    """终止指定进程。"""
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                logger.warning("终止进程失败 [%s]: %s", pid, result.stderr.strip())
                return False
        else:
            os.kill(pid, signal.SIGKILL)
        logger.warning("已终止占用端口的进程: %s", pid)
        return True
    except OSError as exc:
        logger.warning("终止进程失败 [%s]: %s", pid, exc)
        return False
