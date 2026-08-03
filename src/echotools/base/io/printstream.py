"""动态速率打印流：按队列深度自适应输出速度。"""

from __future__ import annotations

import atexit
import math
import sys
import threading
import time
from collections import deque
from typing import Any, Optional


class PrintStream:
    """按队列深度自适应输出速度的打印流。"""

    def __init__(
        self,
        min_speed: float = 5.0,
        max_speed: float = 100.0,
        decay_factor: float = 20.0,
        smoothing_factor: float = 0.8,
    ) -> None:
        # Queue management
        self._text_queue: deque[str] = deque()
        self._current_text: str = ""
        self._lock = threading.Lock()

        # Thread management
        self._running = False
        self._started = False
        self._output_thread: Optional[threading.Thread] = None

        # Speed control parameters
        self.min_speed = max(1.0, min_speed)
        self.max_speed = max(self.min_speed, max_speed)
        self.decay_factor = max(1.0, decay_factor)
        self.smoothing_factor = max(0.1, min(0.99, smoothing_factor))
        self.current_speed = self.min_speed
        self.accumulated_chars = 0.0

        # Statistics
        self.total_pending_chars = 0

    def start(self) -> None:
        """Start the print stream system."""
        if not self._running and not self._started:
            self._running = True
            self._started = True
            self._output_thread = threading.Thread(
                target=self._output_processor, daemon=True
            )
            self._output_thread.start()

    def stop(self) -> None:
        """停止输出；会等待队列中待输出内容排空。"""
        if self._running:
            self._running = False
            # Wait for all content to be output
            max_wait = 10.0
            start_time = time.time()
            while (self._current_text or self._text_queue) and (
                time.time() - start_time
            ) < max_wait:
                time.sleep(0.1)

            if self._output_thread and self._output_thread.is_alive():
                self._output_thread.join(timeout=1)

    def add_to_buffer(self, text: str) -> None:
        """将文本加入输出队列。"""
        if not self._running:
            self.start()

        with self._lock:
            self._text_queue.append(str(text))
            self.total_pending_chars += len(str(text))

    def flush_remaining(self) -> None:
        """Immediately output all remaining content."""
        with self._lock:
            # Output current text being processed
            if self._current_text:
                sys.stdout.write(self._current_text)
                sys.stdout.flush()
                self._current_text = ""

            # Output all text in queue
            while self._text_queue:
                text = self._text_queue.popleft()
                sys.stdout.write(text)
                sys.stdout.flush()

            self.total_pending_chars = 0
            self.accumulated_chars = 0.0

    def _calculate_dynamic_speed(self, buffer_length: int) -> float:
        """根据待输出字符数计算当前输出速率。"""
        if buffer_length <= 0:
            return self.min_speed

        # Combined exponential and logarithmic function
        exp_component = 1 - math.exp(-buffer_length / self.decay_factor)
        log_component = math.log(1 + buffer_length) / math.log(
            1 + self.decay_factor
        )
        combined_factor = (
            2 * exp_component * log_component / (exp_component + log_component + 1e-6)
        )

        # Calculate target speed
        target_speed = self.min_speed + (self.max_speed - self.min_speed) * combined_factor

        # Smooth speed changes
        smooth_speed = (
            self.smoothing_factor * self.current_speed
            + (1 - self.smoothing_factor) * target_speed
        )

        self.current_speed = smooth_speed
        return smooth_speed

    def _write_pending_chars(self, time_delta: float) -> None:
        dynamic_speed = self._calculate_dynamic_speed(self.total_pending_chars)
        chars_to_output = dynamic_speed * time_delta + self.accumulated_chars
        actual_chars = int(chars_to_output)
        self.accumulated_chars = chars_to_output - actual_chars
        if actual_chars <= 0:
            return
        chars_to_print = min(actual_chars, len(self._current_text))
        to_print = self._current_text[:chars_to_print]
        self._current_text = self._current_text[chars_to_print:]
        self.total_pending_chars = max(0, self.total_pending_chars - chars_to_print)
        sys.stdout.write(to_print)
        sys.stdout.flush()

    def _output_processor(self) -> None:
        """Background thread for processing output queue."""
        last_update_time = time.time()

        while self._running or self._current_text or self._text_queue:
            try:
                current_time = time.time()
                time_delta = current_time - last_update_time
                last_update_time = current_time

                with self._lock:
                    if not self._current_text and self._text_queue:
                        self._current_text = self._text_queue.popleft()
                    if self._current_text:
                        self._write_pending_chars(time_delta)

                time.sleep(0.02)

            except Exception:
                if self._current_text:
                    sys.stdout.write(self._current_text)
                    sys.stdout.flush()
                    self._current_text = ""

    @property
    def buffer_size(self) -> int:
        with self._lock:
            queue_chars = sum(len(text) for text in self._text_queue)
            return len(self._current_text) + queue_chars

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def queue_length(self) -> int:
        with self._lock:
            return len(self._text_queue)


# Global instance
_global_print_stream = PrintStream()


def print_stream(
    *args: Any,
    sep: str = " ",
    end: str = "\n",
    flush: bool = False,
) -> None:
    """动态速率 print 替代；flush=True 时立即输出不入队。"""
    try:
        # Ensure system is started
        if not _global_print_stream.is_running:
            _global_print_stream.start()

        # Combine output content
        text = sep.join(str(arg) for arg in args) + end

        if flush:
            # Output immediately
            sys.stdout.write(text)
            sys.stdout.flush()
        else:
            # Add to queue
            _global_print_stream.add_to_buffer(text)

    except Exception:
        # Fallback to standard print on error
        print(*args, sep=sep, end=end)


def start_print_stream() -> None:
    """Manually start the print stream system."""
    _global_print_stream.start()


def stop_print_stream() -> None:
    """Stop the print stream system."""
    _global_print_stream.stop()


def flush_print_stream() -> None:
    """Immediately output all buffered content."""
    _global_print_stream.flush_remaining()


def get_buffer_size() -> int:
    return _global_print_stream.buffer_size


def get_queue_length() -> int:
    return _global_print_stream.queue_length


def is_print_stream_running() -> bool:
    return _global_print_stream.is_running


def set_print_speed(min_speed: float = 5.0, max_speed: float = 50.0) -> None:
    """设置输出速率上下限。"""
    _global_print_stream.min_speed = max(1.0, min_speed)
    _global_print_stream.max_speed = max(_global_print_stream.min_speed, max_speed)


def configure_print_stream(
    min_speed: float = 5.0,
    max_speed: float = 50.0,
    decay_factor: float = 20.0,
    smoothing_factor: float = 0.8,
) -> None:
    """配置输出速率与平滑参数。"""
    _global_print_stream.min_speed = max(1.0, min_speed)
    _global_print_stream.max_speed = max(_global_print_stream.min_speed, max_speed)
    _global_print_stream.decay_factor = max(1.0, decay_factor)
    _global_print_stream.smoothing_factor = max(0.1, min(0.99, smoothing_factor))


def _cleanup() -> None:
    """Cleanup function registered with atexit."""
    try:
        _global_print_stream.flush_remaining()
        _global_print_stream.stop()
    except Exception:
        pass


# Register cleanup function
atexit.register(_cleanup)

__all__ = [
    "PrintStream",
    "print_stream",
    "start_print_stream",
    "stop_print_stream",
    "flush_print_stream",
    "get_buffer_size",
    "get_queue_length",
    "is_print_stream_running",
    "set_print_speed",
    "configure_print_stream",
]