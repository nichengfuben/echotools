from __future__ import annotations

import re
from typing import List, Tuple

THINKING_BLOCK_RE = re.compile(
    r"<entml:thinking\b[^>]*>([\s\S]*?)</entml:thinking>",
    re.DOTALL,
)

_THINKING_OPEN_PREFIX = "<entml:thinking"
_THINKING_CLOSE = "</entml:thinking>"


def has_unclosed_entml_thinking(text: str) -> bool:
    """buffer 中是否存在尚未闭合的 <entml:thinking> 块（含开标签未收齐）。"""
    if not text:
        return False
    i = 0
    while i < len(text):
        open_at = text.find(_THINKING_OPEN_PREFIX, i)
        if open_at < 0:
            break
        gt = text.find(">", open_at)
        if gt < 0:
            return True
        close_at = text.find(_THINKING_CLOSE, gt + 1)
        if close_at < 0:
            return True
        i = close_at + len(_THINKING_CLOSE)
    max_keep = len(_THINKING_OPEN_PREFIX) - 1
    check_len = min(len(text), max_keep)
    for length in range(check_len, 0, -1):
        suffix = text[-length:]
        if _THINKING_OPEN_PREFIX.startswith(suffix) and suffix != _THINKING_OPEN_PREFIX:
            return True
    return False


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


def _hold_prefix(buffer: str, tag: str) -> Tuple[str, str]:
    """若 buffer 尾部是 tag 的真前缀则 hold，否则全部可安全输出。"""
    if not buffer:
        return "", ""
    max_keep = len(tag) - 1
    check_len = min(len(buffer), max_keep)
    for length in range(check_len, 0, -1):
        suffix = buffer[-length:]
        if tag.startswith(suffix) and suffix != tag:
            return buffer[:-length], suffix
    return buffer, ""


class EntmlThinkingStreamFilter:
    """流式拆分 entml:thinking 与可见正文。

    块内正文在收到时即增量输出 thinking，无需等闭合标签。
    """

    def __init__(self) -> None:
        self._pending = ""
        self._in_block = False
        # 当前 thinking 块是否已输出过任何内容（用于首片去前导空白）
        self._thinking_started = False

    def in_open_thinking(self) -> bool:
        """思考块已开始且尚未收到 </entml:thinking>（含开/闭标签分片 hold）。"""
        if self._in_block:
            return True
        open_at = self._pending.find(_THINKING_OPEN_PREFIX)
        if open_at >= 0:
            gt = self._pending.find(">", open_at)
            if gt < 0:
                return True
        _, hold = _hold_prefix(self._pending, _THINKING_OPEN_PREFIX)
        if hold:
            return True
        return False

    def _feed_in_block(self, out: List[Tuple[str, str]]) -> bool:
        """处理块内 pending；返回 False 表示应退出 feed 主循环。"""
        close_at = self._pending.find(_THINKING_CLOSE)
        if close_at >= 0:
            piece = self._pending[:close_at]
            emitted = self._emit_thinking_piece(piece)
            if emitted:
                out.append(("thinking", emitted))
            self._in_block = False
            self._thinking_started = False
            self._pending = self._pending[close_at + len(_THINKING_CLOSE) :]
            return True

        safe, hold = _hold_prefix(self._pending, _THINKING_CLOSE)
        if safe:
            emitted = self._emit_thinking_piece(safe)
            if emitted:
                out.append(("thinking", emitted))
        self._pending = hold
        return False

    def _feed_before_block(self, out: List[Tuple[str, str]]) -> bool:
        """开标签之前或尚未进入块；返回 False 表示应退出 feed 主循环。"""
        open_at = self._pending.find(_THINKING_OPEN_PREFIX)
        if open_at < 0:
            safe, self._pending = _hold_prefix(self._pending, _THINKING_OPEN_PREFIX)
            if safe:
                out.append(("content", safe))
            return False

        if open_at > 0:
            out.append(("content", self._pending[:open_at]))
            self._pending = self._pending[open_at:]

        gt = self._pending.find(">")
        if gt < 0:
            return False

        self._in_block = True
        self._thinking_started = False
        self._pending = self._pending[gt + 1 :]
        return True

    def feed(self, chunk: str) -> List[Tuple[str, str]]:
        """返回 [(kind, text), ...]，kind 为 content 或 thinking。"""
        if not chunk:
            return []

        self._pending += chunk
        out: List[Tuple[str, str]] = []

        while self._pending:
            if self._in_block:
                if not self._feed_in_block(out):
                    break
                continue
            if not self._feed_before_block(out):
                break

        return out

    def _emit_thinking_piece(self, piece: str) -> str:
        """输出 thinking 片段；首片去掉前导空白，与 batch strip 对齐。"""
        if not piece:
            return ""
        if not self._thinking_started:
            piece = piece.lstrip()
            if not piece:
                return ""
            self._thinking_started = True
        return piece

    def finalize(self) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        if self._in_block:
            # 未闭合：剩余 pending（含可能 hold 的关闭标签前缀）视作思考
            emitted = self._emit_thinking_piece(self._pending)
            if emitted:
                out.append(("thinking", emitted))
        elif self._pending:
            content, thinking = split_entml_thinking(self._pending)
            if thinking:
                out.append(("thinking", thinking))
            if content:
                out.append(("content", content))
            elif self._pending and not thinking:
                # 仅 hold 了半截开标签：原样吐出，避免吞字
                out.append(("content", self._pending))
        self._pending = ""
        self._in_block = False
        self._thinking_started = False
        return out
