"""FncallStreamParser streaming delta helpers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class StreamDeltaMixin:
    def _is_call_closed(self) -> bool:
        """检测 fncall 缓冲区中是否包含结束标记。"""
        if self._no_auto_close:
            return False
        buf = self._fncall_buf
        for end_tag in self._end_tags:
            if end_tag in buf:
                return True
        return False

    def _stream_active_invoke_slot(self) -> int:
        """当前正在流式编码的 invoke 序号（0-based）。"""
        from echotools.exec.fncall.protocols.entml_patterns import INVOKE_RE
        from echotools.exec.fncall.protocols.entml_stream import (
            _INVOKE_CLOSE,
            _INVOKE_OPEN_PREFIX,
            split_invoke_open,
        )

        complete = list(INVOKE_RE.finditer(self._fncall_buf))
        complete_n = len(complete)
        parsed = split_invoke_open(self._fncall_buf)
        if parsed is None:
            return max(0, complete_n - 1)
        _name, body_start = parsed
        body = self._fncall_buf[body_start:]
        if _INVOKE_CLOSE in body:
            return max(0, complete_n - 1)
        open_pos = self._fncall_buf.rfind(_INVOKE_OPEN_PREFIX)
        if complete and open_pos >= complete[-1].end():
            return complete_n
        return max(0, complete_n - 1)

    def _merge_or_append_pending_delta(self, name: str, piece: str, slot: int) -> None:
        if not piece:
            return
        if self._pending_stream_deltas and self._pending_stream_deltas[-1][2] == slot:
            prev_name, prev_piece, prev_slot = self._pending_stream_deltas[-1]
            self._pending_stream_deltas[-1] = (prev_name, prev_piece + piece, prev_slot)
        else:
            self._pending_stream_deltas.append((name, piece, slot))

    def _pending_body_for_name(self, name: str) -> str:
        return "".join(p for n, p in self._pending_stream_deltas if n == name)

    def _track_stream_delta(self, name: str, piece: str) -> None:
        slot = self._stream_active_invoke_slot()
        while len(self._stream_invoke_emitted) <= slot:
            self._stream_invoke_emitted.append("")
        self._stream_invoke_emitted[slot] += piece
        self._merge_or_append_pending_delta(name, piece, slot)

    def _ready_call_tail(self, call, prev: str, *, multi: bool) -> str:
        final = call["function"]["arguments"]
        if final.startswith(prev):
            return final[len(prev) :]
        if prev:
            return ""
        pname = call["function"]["name"]
        pending_body = self._pending_body_for_name(pname) if not multi else ""
        if final.startswith(pending_body):
            return final[len(pending_body) :]
        return final if not pending_body else ""

    def _align_json_encoder_after_ready(self) -> None:
        if self._json_stream_encoder is None:
            return
        from echotools.exec.fncall.protocols.entml_stream import (
            _INVOKE_CLOSE,
            build_streaming_json_snapshot,
            split_invoke_open,
        )
        parsed = split_invoke_open(self._fncall_buf)
        if not parsed:
            self._json_stream_encoder.reset()
            return
        name, body_start = parsed
        body = self._fncall_buf[body_start:]
        if _INVOKE_CLOSE in body:
            self._json_stream_encoder.reset()
            return
        snap = build_streaming_json_snapshot(
            body, tool_name=name, schema_index=self._get_schema_index()
        )
        self._json_stream_encoder.set_tool_context(name, self._get_schema_index())
        self._json_stream_encoder._emitted = snap

    def _ensure_ready_invoke_stream_tails(
        self, ready: List[Dict[str, Any]]
    ) -> None:
        """invoke ready 时补齐 partial_json 尾部，避免大 chunk 下缺 ``}``。"""
        if not ready:
            return
        base = self._emitted_invoke_count - len(ready)
        multi = len(ready) > 1
        if multi:
            self._pending_stream_deltas.clear()
        for offset, call in enumerate(ready):
            idx = base + offset
            while len(self._stream_invoke_emitted) <= idx:
                self._stream_invoke_emitted.append("")
            prev = self._stream_invoke_emitted[idx]
            tail = self._ready_call_tail(call, prev, multi=multi)
            if tail:
                name = call["function"]["name"]
                if multi:
                    self._pending_stream_deltas.append((name, tail, idx))
                else:
                    self._merge_or_append_pending_delta(name, tail, idx)
            self._stream_invoke_emitted[idx] = call["function"]["arguments"]
        self._align_json_encoder_after_ready()

    def _sync_json_stream_encoder_emitted(self) -> None:
        """invoke 已 ready 后对齐 encoder，避免下一 chunk 重发整段 partial_json。"""
        if self._json_stream_encoder is None:
            return
        from echotools.exec.fncall.protocols.entml_stream import (
            split_invoke_open,
        )

        parsed = split_invoke_open(self._fncall_buf)
        if not parsed:
            self._json_stream_encoder.reset()
            return
        name, body_start = parsed
        body = self._fncall_buf[body_start:]
        self._json_stream_encoder.poll(body)

    def feed(self, chunk: str) -> List[Dict[str, Any]]:
        """喂入新的流式文本块。

        返回本轮新完成的 tool_calls（与 ``get_ready_tool_calls()`` 相同语义：
        调用后计数前进，勿再对本轮结果重复调用 ``get_ready_tool_calls``）。
        DONE 或 finalize 后调用返回 ``[]``。
        """
        if not chunk or self._state == self.DONE:
            return []
        if self._finalized_result is not None:
            return []

        self._raw_buf += chunk

        if self._state != self.DONE:
            self._feed_waiting(chunk)

        polled = self._poll_streaming_tool_input_delta()
        if polled:
            self._track_stream_delta(polled[0], polled[1])
        ready = self.get_ready_tool_calls()
        if ready:
            self._ensure_ready_invoke_stream_tails(ready)
        return ready

    def _poll_streaming_tool_input_delta(self) -> Optional[Tuple[str, str]]:
        """invoke 开标签完整匹配后，返回 (tool_name, partial_json_delta)。"""
        if not self._detected or getattr(self._protocol, "id", None) != "entml":
            return None
        if self._state not in (self.IN_FUNCTION_CALLS,):
            return None
        from echotools.exec.fncall.protocols.entml_patterns import INVOKE_RE
        from echotools.exec.fncall.protocols.entml_stream import (
            _INVOKE_CLOSE,
            EntmlInvokeJsonStreamEncoder,
            build_streaming_json_snapshot,
            split_invoke_open,
        )

        parsed = split_invoke_open(self._fncall_buf)
        if not parsed:
            return None
        name, body_start = parsed
        body = self._fncall_buf[body_start:]
        complete = list(INVOKE_RE.finditer(self._fncall_buf))
        complete_n = len(complete)
        if _INVOKE_CLOSE in body:
            if complete_n <= self._emitted_invoke_count:
                return None
            # 同一 chunk 内多个 invoke 同时闭合时，由 ensure 按序入队，避免只 poll 最后一个
            if complete_n - self._emitted_invoke_count > 1:
                return None
            slot = max(0, complete_n - 1)
            schema_index = self._get_schema_index()
            final = build_streaming_json_snapshot(
                body,
                tool_name=name,
                schema_index=schema_index,
            )
            while len(self._stream_invoke_emitted) <= slot:
                self._stream_invoke_emitted.append("")
            if self._stream_invoke_emitted[slot] == final:
                return None
        schema_index = self._get_schema_index()
        if self._json_stream_encoder is None:
            self._json_stream_encoder = EntmlInvokeJsonStreamEncoder(
                tool_name=name,
                schema_index=schema_index,
            )
        else:
            self._json_stream_encoder.set_tool_context(name, schema_index)
        delta = self._json_stream_encoder.poll(body)
        if not delta:
            return None
        return (name, delta)

    def consume_stream_delta(self) -> Optional[Tuple[str, str]]:
        """取出本轮 ``feed`` 产生的 streaming partial_json 增量（FIFO，可多段）。"""
        if not self._pending_stream_deltas:
            return None
        name, piece, _slot = self._pending_stream_deltas.popleft()
        return (name, piece)

    def stream_invoke_argument_snapshots(self) -> List[str]:
        """各 invoke slot 已流式发出的 arguments JSON 累积（与 batch 对齐）。"""
        return list(self._stream_invoke_emitted)

    @property
    def streaming_invoke_closed(self) -> bool:
        """流式 fncall 缓冲中是否已出现 ``</entml:invoke>``。"""
        if getattr(self._protocol, "id", None) != "entml":
            return False
        from echotools.exec.fncall.protocols.entml_stream import _INVOKE_CLOSE

        return _INVOKE_CLOSE in self._fncall_buf

    def complete_stream_delta_if_needed(self) -> Optional[Tuple[str, str]]:
        """invoke 已开标签但未闭合时，补齐 partial_json 尾部的合法 JSON 后缀。"""
        if not self._detected or getattr(self._protocol, "id", None) != "entml":
            return None
        if self.streaming_invoke_closed:
            return None
        from echotools.exec.fncall.protocols.entml_stream import (
            EntmlInvokeJsonStreamEncoder,
            build_streaming_json_snapshot,
            split_invoke_open,
        )

        parsed = split_invoke_open(self._fncall_buf)
        if not parsed:
            return None
        name, body_start = parsed
        body = self._fncall_buf[body_start:]
        schema_index = self._get_schema_index()
        snapshot = build_streaming_json_snapshot(
            body,
            tool_name=name,
            schema_index=schema_index,
            force_close=True,
        )
        if not snapshot:
            return None
        if self._json_stream_encoder is None:
            self._json_stream_encoder = EntmlInvokeJsonStreamEncoder(
                tool_name=name,
                schema_index=schema_index,
            )
        else:
            self._json_stream_encoder.set_tool_context(name, schema_index)
        delta = self._json_stream_encoder.poll(body, force_close=True)
        if not delta:
            return None
        return (name, delta)

