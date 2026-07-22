from __future__ import annotations

import re
from typing import List, Tuple

THINKING_BLOCK_RE = re.compile(
    r"<entml:thinking\b[^>]*>([\s\S]*?)</entml:thinking>",
    re.DOTALL,
)

_THINKING_OPEN_PREFIX = "<entml:thinking"
_THINKING_CLOSE = "</entml:thinking>"


def split_entml_thinking(text: str) -> Tuple[str, str]:
    """从文本中剥离 <entml:thinking> 块，返回 (正文, 思考链拼接)。"""
    if not text:
        return "", ""

    parts: List[str] = []

    def _collect(match: re.Match[str]) -> str:
        parts.append(match.group(1))
        return ""

    clean = THINKING_BLOCK_RE.sub(_collect, text)
    thinking = "\n".join(part.strip() for part in parts if part.strip())
    return clean.strip(), thinking


def _split_safe_prefix(buffer: str) -> Tuple[str, str]:
    """保留可能未闭合的 <entml:thinking 开标签尾部。"""
    if not buffer:
        return "", ""

    open_pos = buffer.rfind(_THINKING_OPEN_PREFIX)
    if open_pos < 0:
        return buffer, ""

    tail = buffer[open_pos:]
    if ">" in tail and _THINKING_CLOSE not in tail:
        return buffer, ""

    close_pos = buffer.rfind(_THINKING_CLOSE)
    if close_pos >= 0 and close_pos > open_pos:
        return buffer, ""

    if tail == _THINKING_OPEN_PREFIX[: len(tail)]:
        return buffer[:open_pos], tail

    return buffer[:open_pos], tail


class EntmlThinkingStreamFilter:
    """流式拆分 entml:thinking 与可见正文。"""

    def __init__(self) -> None:
        self._pending = ""
        self._in_block = False
        self._block_buf = ""

    def feed(self, chunk: str) -> List[Tuple[str, str]]:
        """返回 [(kind, text), ...]，kind 为 content 或 thinking。"""
        if not chunk:
            return []

        self._pending += chunk
        out: List[Tuple[str, str]] = []

        while self._pending:
            if self._in_block:
                close_at = self._pending.find(_THINKING_CLOSE)
                if close_at < 0:
                    self._block_buf += self._pending
                    self._pending = ""
                    break
                self._block_buf += self._pending[:close_at]
                thinking = self._block_buf.strip()
                if thinking:
                    out.append(("thinking", thinking))
                self._block_buf = ""
                self._in_block = False
                self._pending = self._pending[close_at + len(_THINKING_CLOSE) :]
                continue

            open_at = self._pending.find(_THINKING_OPEN_PREFIX)
            if open_at < 0:
                safe, self._pending = _split_safe_prefix(self._pending)
                if safe:
                    out.append(("content", safe))
                break

            if open_at > 0:
                prefix = self._pending[:open_at]
                out.append(("content", prefix))
                self._pending = self._pending[open_at:]

            gt = self._pending.find(">")
            if gt < 0:
                break

            self._in_block = True
            self._pending = self._pending[gt + 1 :]

        return out

    def finalize(self) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        if self._in_block:
            thinking = (self._block_buf + self._pending).strip()
            if thinking:
                out.append(("thinking", thinking))
        elif self._pending:
            content, thinking = split_entml_thinking(self._pending)
            if thinking:
                out.append(("thinking", thinking))
            if content:
                out.append(("content", content))
        self._pending = ""
        self._block_buf = ""
        self._in_block = False
        return out
