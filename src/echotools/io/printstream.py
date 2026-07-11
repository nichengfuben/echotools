"""Dynamic speed print stream system for controlled console output.

This module provides a PrintStream class that implements dynamic speed
printing with ordered queue management, suitable for controlled output
of large text blocks with adaptive speed based on queue depth.
"""

from __future__ import annotations

import atexit
import math
import sys
import threading
import time
from collections import deque
from typing import Any, Optional


class PrintStream:
    """Dynamic speed print stream system with ordered queue.

    This class manages a queue of text blocks and outputs them with
    adaptive speed based on the current queue depth. The output speed
    increases as more text is pending, providing smooth, controlled output.

    Attributes:
        min_speed: Minimum output speed in characters per second.
        max_speed: Maximum output speed in characters per second.
        decay_factor: Controls how quickly speed adapts to queue depth.
        smoothing_factor: Controls speed change smoothing (0.0-1.0).
        current_speed: Current output speed in characters per second.
        accumulated_chars: Fractional characters pending output.
        total_pending_chars: Total characters waiting to be output.
    """

    def __init__(
        self,
        min_speed: float = 5.0,
        max_speed: float = 100.0,
        decay_factor: float = 20.0,
        smoothing_factor: float = 0.8,
    ) -> None:
        """Initialize the print stream.

        Args:
            min_speed: Minimum output speed (characters/second).
            max_speed: Maximum output speed (characters/second).
            decay_factor: Controls speed adaptation curve.
            smoothing_factor: Controls speed change smoothing.
        """
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
        """Stop the print stream system.

        Waits for all pending output to complete before stopping.
        """
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
        """Add text to the output queue.

        Args:
            text: Text to add to the queue.
        """
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
        """Calculate dynamic output speed based on buffer length.

        Args:
            buffer_length: Number of pending characters.

        Returns:
            Calculated speed in characters per second.
        """
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

    def _output_processor(self) -> None:
        """Background thread for processing output queue."""
        last_update_time = time.time()

        while self._running or self._current_text or self._text_queue:
            try:
                current_time = time.time()
                time_delta = current_time - last_update_time
                last_update_time = current_time

                with self._lock:
                    # If no current text, get next from queue
                    if not self._current_text and self._text_queue:
                        self._current_text = self._text_queue.popleft()

                    # If there's text to output
                    if self._current_text:
                        # Calculate dynamic speed based on total pending chars
                        dynamic_speed = self._calculate_dynamic_speed(
                            self.total_pending_chars
                        )

                        # Calculate characters to output this iteration
                        chars_to_output = dynamic_speed * time_delta + self.accumulated_chars
                        actual_chars = int(chars_to_output)
                        self.accumulated_chars = chars_to_output - actual_chars

                        # Output characters
                        if actual_chars > 0:
                            chars_to_print = min(actual_chars, len(self._current_text))
                            to_print = self._current_text[:chars_to_print]
                            self._current_text = self._current_text[chars_to_print:]

                            # Update total pending chars
                            self.total_pending_chars = max(
                                0, self.total_pending_chars - chars_to_print
                            )

                            # Output to console
                            sys.stdout.write(to_print)
                            sys.stdout.flush()

                # Brief sleep to control update frequency
                time.sleep(0.02)  # 50Hz update rate

            except Exception:
                # Error handling: output remaining content directly
                if self._current_text:
                    sys.stdout.write(self._current_text)
                    sys.stdout.flush()
                    self._current_text = ""

    @property
    def buffer_size(self) -> int:
        """Get total characters waiting to be output.

        Returns:
            Number of pending characters.
        """
        with self._lock:
            queue_chars = sum(len(text) for text in self._text_queue)
            return len(self._current_text) + queue_chars

    @property
    def is_running(self) -> bool:
        """Check if the system is running.

        Returns:
            True if running, False otherwise.
        """
        return self._running

    @property
    def queue_length(self) -> int:
        """Get number of text blocks in queue.

        Returns:
            Number of queued text blocks.
        """
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
    """Dynamic speed print function.

    This function provides a drop-in replacement for the built-in print()
    function with dynamic speed output based on queue depth.

    Args:
        *args: Content to print.
        sep: Separator between arguments (default: space).
        end: End character (default: newline).
        flush: If True, output immediately without queuing.
    """
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
    """Get current buffer size.

    Returns:
        Number of pending characters.
    """
    return _global_print_stream.buffer_size


def get_queue_length() -> int:
    """Get number of text blocks in queue.

    Returns:
        Number of queued text blocks.
    """
    return _global_print_stream.queue_length


def is_print_stream_running() -> bool:
    """Check if the print stream system is running.

    Returns:
        True if running, False otherwise.
    """
    return _global_print_stream.is_running


def set_print_speed(min_speed: float = 5.0, max_speed: float = 50.0) -> None:
    """Set print speed range.

    Args:
        min_speed: Minimum print speed (characters/second).
        max_speed: Maximum print speed (characters/second).
    """
    _global_print_stream.min_speed = max(1.0, min_speed)
    _global_print_stream.max_speed = max(_global_print_stream.min_speed, max_speed)


def configure_print_stream(
    min_speed: float = 5.0,
    max_speed: float = 50.0,
    decay_factor: float = 20.0,
    smoothing_factor: float = 0.8,
) -> None:
    """Configure print stream system parameters.

    Args:
        min_speed: Minimum print speed.
        max_speed: Maximum print speed.
        decay_factor: Decay factor for speed adaptation.
        smoothing_factor: Smoothing factor for speed changes.
    """
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


# Module exports
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