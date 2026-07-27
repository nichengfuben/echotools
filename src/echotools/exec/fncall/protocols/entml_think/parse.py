from __future__ import annotations

import re
from typing import List, Tuple

from echotools.exec.fncall.protocols.entml_patterns import (
    extract_attr_value,
    normalize_entml_name,
)

THINKING_BLOCK_RE = re.compile(
    r"<entml:thinking\b[^>]*>([\s\S]*?)</entml:thinking>",
    re.DOTALL,
)

_THINKING_OPEN_PREFIX = "<entml:thinking"
_THINKING_CLOSE = "</entml:thinking>"
_FAULT_THINKING_CLOSE = "</thinking>"
# 与 thinking 共享 `<entml:` 前缀的其它标签：歧义 holdback 应交由工具流式状态机处理
_AMBIGUOUS_ENTML_PREFIXES = (
    "<entml:invoke",
    "<entml:function_calls",
    "<entml:parameter",
    "<entml:parameters",
)
_INVOKE_PREFIX = "<entml:invoke"


def find_complete_entml_invoke_open(buffer: str) -> int:
    """返回首个含 name 且已闭合 ``>`` 的 ``<entml:invoke`` 起始下标；否则 -1。"""
    if not buffer:
        return -1
    search_from = 0
    prefix_len = len(_INVOKE_PREFIX)
    while True:
        pos = buffer.find(_INVOKE_PREFIX, search_from)
        if pos < 0:
            return -1
        close = buffer.find(">", pos + prefix_len)
        if close < 0:
            return -1
        attrs = buffer[pos + prefix_len : close]
        name = extract_attr_value(attrs, "name")
        if name and normalize_entml_name(name):
            return pos
        search_from = close + 1


def find_ambiguous_entml_tool_prefix(buffer: str) -> int:
    """thinking 块内出现工具相关 entml 前缀时，最早的下标（含未收齐的开标签）。"""
    if not buffer:
        return -1
    earliest = -1
    for prefix in _AMBIGUOUS_ENTML_PREFIXES:
        pos = buffer.find(prefix)
        if pos >= 0 and (earliest < 0 or pos < earliest):
            earliest = pos
    return earliest


def _hold_ambiguous_tool_markup(buffer: str) -> Tuple[str, str]:
    """thinking 块内：尾部是工具 entml 标签真前缀时 hold，避免误当 thinking 吐出。"""
    if not buffer:
        return "", ""
    lt = buffer.rfind("<")
    if lt < 0:
        return buffer, ""
    tail = buffer[lt:]
    for prefix in _AMBIGUOUS_ENTML_PREFIXES:
        if prefix.startswith(tail) and tail != prefix:
            return buffer[:lt], tail
    return buffer, ""


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
        if not (
            _THINKING_OPEN_PREFIX.startswith(suffix) and suffix != _THINKING_OPEN_PREFIX
        ):
            continue
        # `<e` / `<entml:` 等对 invoke 同样是真前缀 → 不在此抢占
        if any(other.startswith(suffix) for other in _AMBIGUOUS_ENTML_PREFIXES):
            continue
        return True
    return False


def invoke_index_inside_unclosed_thinking(text: str, invoke_at: int) -> bool:
    """``invoke_at`` 是否落在尚未正式 ``</entml:thinking>`` 闭合的块内。

    已出现容错 ``</thinking>`` 且 invoke 在其后的段落，视为 thinking 外。
    """
    if invoke_at < 0:
        return False
    think_open = text.find(_THINKING_OPEN_PREFIX)
    if think_open < 0 or invoke_at <= think_open:
        return False
    entml_close = text.find(_THINKING_CLOSE, think_open)
    if entml_close >= 0:
        return invoke_at < entml_close
    fault_at = text.find(_FAULT_THINKING_CLOSE, think_open)
    if fault_at >= 0:
        return invoke_at < fault_at + len(_FAULT_THINKING_CLOSE)
    return True


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
        # 见到 ``</thinking>`` 后暂存，仅当后续出现 invoke 才视为闭合；否则当纯文本
        self._fault_watch = False
        self._fault_buffer = ""

    def in_open_thinking(self) -> bool:
        """思考块已开始且尚未收到 ``</entml:thinking>``（含开/闭标签分片 hold）。"""
        if self._in_block or self._fault_watch:
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

    def _try_resolve_fault_watch_on_invoke(self) -> bool:
        """``</thinking>`` 之后若出现完整 invoke 开标签，则在该处结束 thinking。"""
        if not self._fault_watch or not self._fault_buffer:
            return False
        invoke_at = find_complete_entml_invoke_open(self._fault_buffer)
        if invoke_at < len(_FAULT_THINKING_CLOSE):
            return False
        self._in_block = False
        self._fault_watch = False
        self._thinking_started = False
        self._pending = self._fault_buffer[len(_FAULT_THINKING_CLOSE) :]
        self._fault_buffer = ""
        return True

    def _try_resolve_fault_watch_on_entml_close(self, out: List[Tuple[str, str]]) -> bool:
        """未见 invoke 时出现 ``</entml:thinking>`` → ``</thinking>`` 仅为思考内纯文本。"""
        if not self._fault_watch:
            return False
        close_at = self._fault_buffer.find(_THINKING_CLOSE)
        if close_at < 0:
            return False
        emitted = self._emit_thinking_piece(self._fault_buffer[:close_at])
        if emitted:
            out.append(("thinking", emitted))
        self._in_block = False
        self._fault_watch = False
        self._thinking_started = False
        self._pending = self._fault_buffer[close_at + len(_THINKING_CLOSE) :]
        self._fault_buffer = ""
        return True

    def _feed_fault_watch(self, out: List[Tuple[str, str]]) -> bool:
        """处理 ``</thinking>`` 容错观察期；返回 True 表示可继续主循环。"""
        if self._try_resolve_fault_watch_on_invoke():
            return True
        if self._try_resolve_fault_watch_on_entml_close(out):
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
            self._fault_watch = False
            self._fault_buffer = ""
            self._thinking_started = False
            self._pending = self._pending[close_at + len(_THINKING_CLOSE) :]
            return True

        fault_at = self._pending.find(_FAULT_THINKING_CLOSE)
        if fault_at >= 0:
            before = self._pending[:fault_at]
            emitted = self._emit_thinking_piece(before)
            if emitted:
                out.append(("thinking", emitted))
            self._fault_watch = True
            self._fault_buffer = self._pending[fault_at:]
            self._pending = ""
            return False

        safe, tool_hold = _hold_ambiguous_tool_markup(self._pending)
        if tool_hold:
            if safe:
                emitted = self._emit_thinking_piece(safe)
                if emitted:
                    out.append(("thinking", emitted))
            self._pending = tool_hold
            return False

        safe, hold = _hold_prefix(self._pending, _THINKING_CLOSE)
        if not hold:
            safe, hold = _hold_prefix(safe, _FAULT_THINKING_CLOSE)
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
            if self._fault_watch:
                self._fault_buffer += self._pending
                self._pending = ""
                if self._feed_fault_watch(out):
                    continue
                break
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
        if self._fault_watch:
            if self._try_resolve_fault_watch_on_invoke():
                pass
            elif self._try_resolve_fault_watch_on_entml_close(out):
                pass
            else:
                emitted = self._emit_thinking_piece(self._fault_buffer)
                if emitted:
                    out.append(("thinking", emitted))
                self._fault_buffer = ""
                self._fault_watch = False
                self._in_block = False
                self._thinking_started = False
        if self._in_block:
            emitted = self._emit_thinking_piece(self._pending)
            if emitted:
                out.append(("thinking", emitted))
            self._pending = ""
            self._in_block = False
            self._thinking_started = False
        if self._pending:
            content, thinking = split_entml_thinking(self._pending)
            if thinking:
                out.append(("thinking", thinking))
            if content:
                out.append(("content", content))
            elif self._pending and not thinking:
                out.append(("content", self._pending))
        self._pending = ""
        self._in_block = False
        self._fault_watch = False
        self._fault_buffer = ""
        self._thinking_started = False
        return out
