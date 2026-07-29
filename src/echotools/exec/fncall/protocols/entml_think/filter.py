from __future__ import annotations

import re
from typing import List, Optional, Tuple

from echotools.exec.fncall.protocols.entml_patterns import (
    entml_invoke_open_may_be_streaming,
    extract_attr_value,
    normalize_entml_name,
)

THINKING_BLOCK_RE = re.compile(
    r"<entml:thinking\b[^>]*>([\s\S]*?)</entml:thinking>",
    re.DOTALL,
)

_THINKING_OPEN_PREFIX = "<entml:thinking"
_PLAIN_THINKING_OPEN_PREFIX = "<thinking"
_THINKING_CLOSE = "</entml:thinking>"
_FAULT_THINKING_CLOSE = "</thinking>"
_ORPHAN_CLOSE_PREFIXES = (
    "</entml:thinking",
    "</thinking",
)
# 与 thinking 共享 `<entml:` 前缀的其它标签：歧义 holdback 应交由工具流式状态机处理
_AMBIGUOUS_ENTML_PREFIXES = (
    "<entml:invoke",
    "<entml:function_calls",
    "<entml:parameter",
    "<entml:parameters",
)
_INVOKE_PREFIX = "<entml:invoke"
_FUNCTION_CALLS_PREFIX = "<entml:function_calls"
_LEADING_HOLD_PREFIXES = _AMBIGUOUS_ENTML_PREFIXES + _ORPHAN_CLOSE_PREFIXES + (
    _THINKING_OPEN_PREFIX,
    _FUNCTION_CALLS_PREFIX,
    "<tool",
    "<assistant",
)

from echotools.exec.fncall.protocols.entml_think.hold import (
    _FAULT_THINKING_CLOSE,
    _THINKING_CLOSE,
    _THINKING_OPEN_PREFIX,
    _PLAIN_THINKING_OPEN_PREFIX,
    _INVOKE_PREFIX,
    _find_earliest_thinking_open,
    _find_thinking_close,
    _hold_ambiguous_tool_markup,
    _hold_prefix,
    _hold_thinking_open_prefixes,
    find_complete_entml_invoke_open,
    tool_markup_follows_entml_thinking_close,
)

class EntmlThinkingStreamFilter:
    """流式拆分 entml:thinking 与可见正文。

    块内正文在收到时即增量输出 thinking，无需等闭合标签。
    """

    def __init__(self, *, thinking_enabled: bool = True) -> None:
        self._thinking_enabled = thinking_enabled
        self._pending = ""
        self._in_block = False
        self._opened_plain = False
        # 当前 thinking 块是否已输出过任何内容（用于首片去前导空白）
        self._thinking_started = False
        # 见到 ``</thinking>`` 后暂存，仅当后续出现 invoke 才视为闭合；否则当纯文本
        self._fault_watch = False
        self._fault_buffer = ""

    def clear_invoke_handoff_state(self) -> None:
        """invoke 已交给正文/工具解析后，结束 thinking / fault 观察状态。"""
        self._in_block = False
        self._opened_plain = False
        self._fault_watch = False
        self._fault_buffer = ""
        self._thinking_started = False

    def in_open_thinking(self) -> bool:
        """思考块已开始且尚未闭合（含开/闭标签分片 hold）。"""
        if self._in_block or self._fault_watch:
            return True
        open_at, _ = _find_earliest_thinking_open(
            self._pending, thinking_enabled=self._thinking_enabled
        )
        if open_at >= 0:
            gt = self._pending.find(">", open_at)
            if gt < 0:
                return True
        _, hold = _hold_thinking_open_prefixes(
            self._pending, thinking_enabled=self._thinking_enabled
        )
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
        self._opened_plain = False
        self._fault_watch = False
        self._thinking_started = False
        self._pending = self._fault_buffer[len(_FAULT_THINKING_CLOSE) :]
        self._fault_buffer = ""
        return True

    def _try_resolve_fault_watch_on_entml_close(self, out: List[Tuple[str, str]]) -> bool:
        """未见 invoke 时出现 ``</entml:thinking>`` → 若其后为 tool/invoke 则中间段为可见正文。"""
        if not self._fault_watch:
            return False
        close_at = self._fault_buffer.find(_THINKING_CLOSE)
        if close_at < 0:
            return False
        after_entml = self._fault_buffer[close_at + len(_THINKING_CLOSE) :]
        if tool_markup_follows_entml_thinking_close(after_entml):
            middle = self._fault_buffer[len(_FAULT_THINKING_CLOSE) : close_at]
            visible = middle.strip()
            if visible:
                out.append(("content", visible))
        else:
            emitted = self._emit_thinking_piece(self._fault_buffer[:close_at])
            if emitted:
                out.append(("thinking", emitted))
        self._in_block = False
        self._opened_plain = False
        self._fault_watch = False
        self._thinking_started = False
        self._pending = after_entml
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
            if piece:
                emitted = self._emit_thinking_piece(piece)
                if emitted:
                    out.append(("thinking", emitted))
            self._in_block = False
            self._opened_plain = False
            self._fault_watch = False
            self._fault_buffer = ""
            self._thinking_started = False
            self._pending = self._pending[close_at + len(_THINKING_CLOSE) :]
            return True

        fault_at = self._pending.find(_FAULT_THINKING_CLOSE)
        if fault_at >= 0 and self._thinking_enabled:
            before = self._pending[:fault_at]
            if self._opened_plain:
                emitted = self._emit_thinking_piece(before)
                if emitted:
                    out.append(("thinking", emitted))
                self._in_block = False
                self._opened_plain = False
                self._fault_watch = False
                self._fault_buffer = ""
                self._thinking_started = False
                self._pending = self._pending[fault_at + len(_FAULT_THINKING_CLOSE) :]
                return True
            emitted = self._emit_thinking_piece(before)
            if emitted:
                out.append(("thinking", emitted))
            self._fault_watch = True
            self._fault_buffer = self._pending[fault_at:]
            self._pending = ""
            return False

        # thinking 块内 ``<entml:invoke>`` 等仅为 prose/示例时仍计入 thinking，不按工具 hold 截断。
        safe, hold = _hold_prefix(self._pending, _THINKING_CLOSE)
        if not hold and self._thinking_enabled:
            safe, hold = _hold_prefix(safe, _FAULT_THINKING_CLOSE)
        if safe:
            emitted = self._emit_thinking_piece(safe)
            if emitted:
                out.append(("thinking", emitted))
        self._pending = hold
        return False

    def _feed_before_block(self, out: List[Tuple[str, str]]) -> bool:
        """开标签之前或尚未进入块；返回 False 表示应退出 feed 主循环。"""
        open_at, opened_plain = _find_earliest_thinking_open(
            self._pending, thinking_enabled=self._thinking_enabled
        )
        if open_at < 0:
            safe, self._pending = _hold_thinking_open_prefixes(
                self._pending, thinking_enabled=self._thinking_enabled
            )
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
        self._opened_plain = opened_plain
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
                self._opened_plain = False
                self._thinking_started = False
        if self._in_block:
            emitted = self._emit_thinking_piece(self._pending)
            if emitted:
                out.append(("thinking", emitted))
            self._pending = ""
            self._in_block = False
            self._opened_plain = False
            self._thinking_started = False
        if self._pending:
            from echotools.exec.fncall.protocols.entml_think.parse import (
                split_entml_thinking,
            )

            content, thinking = split_entml_thinking(
                self._pending, thinking_enabled=self._thinking_enabled
            )
            if thinking:
                out.append(("thinking", thinking))
            if content:
                out.append(("content", content))
            elif self._pending and not thinking:
                out.append(("content", self._pending))
        self._pending = ""
        self._in_block = False
        self._opened_plain = False
        self._fault_watch = False
        self._fault_buffer = ""
        self._thinking_started = False
        return out
