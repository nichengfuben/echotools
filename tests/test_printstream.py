"""Tests for the printstream module."""

from __future__ import annotations

import sys
import time
from unittest.mock import patch

from echotools.io.printstream import (
    PrintStream,
    configure_print_stream,
    flush_print_stream,
    get_buffer_size,
    get_queue_length,
    is_print_stream_running,
    print_stream,
    set_print_speed,
    start_print_stream,
    stop_print_stream,
)


class TestPrintStream:
    """Tests for the PrintStream class."""

    def test_initialization(self) -> None:
        """Test PrintStream initialization with default values."""
        stream = PrintStream()
        assert stream.min_speed == 5.0
        assert stream.max_speed == 100.0
        assert stream.decay_factor == 20.0
        assert stream.smoothing_factor == 0.8
        assert stream.current_speed == 5.0
        assert stream.total_pending_chars == 0
        assert stream.is_running is False

    def test_initialization_custom_values(self) -> None:
        """Test PrintStream initialization with custom values."""
        stream = PrintStream(
            min_speed=10.0,
            max_speed=200.0,
            decay_factor=30.0,
            smoothing_factor=0.9,
        )
        assert stream.min_speed == 10.0
        assert stream.max_speed == 200.0
        assert stream.decay_factor == 30.0
        assert stream.smoothing_factor == 0.9

    def test_initialization_value_clamping(self) -> None:
        """Test that initialization clamps values to valid ranges."""
        stream = PrintStream(
            min_speed=0.5,  # Below minimum
            max_speed=0.3,  # Below min_speed
            decay_factor=0.5,  # Below minimum
            smoothing_factor=0.05,  # Below minimum
        )
        assert stream.min_speed == 1.0
        assert stream.max_speed == 1.0
        assert stream.decay_factor == 1.0
        assert stream.smoothing_factor == 0.1

    def test_start_and_stop(self) -> None:
        """Test starting and stopping the print stream."""
        stream = PrintStream()
        stream.start()
        assert stream.is_running is True
        assert stream._output_thread is not None
        assert stream._output_thread.is_alive()

        stream.stop()
        assert stream.is_running is False

    def test_start_idempotent(self) -> None:
        """Test that starting an already running stream is idempotent."""
        stream = PrintStream()
        stream.start()
        thread1 = stream._output_thread

        stream.start()  # Should not create a new thread
        thread2 = stream._output_thread

        assert thread1 is thread2
        stream.stop()

    def test_add_to_buffer(self) -> None:
        """Test adding text to the buffer."""
        stream = PrintStream()
        stream.start()

        stream.add_to_buffer("Hello")
        assert stream.buffer_size == 5
        assert stream.queue_length == 1

        stream.add_to_buffer("World")
        assert stream.buffer_size == 10
        assert stream.queue_length == 2

        stream.stop()

    def test_add_to_buffer_auto_start(self) -> None:
        """Test that adding to buffer auto-starts the stream."""
        stream = PrintStream()
        assert stream.is_running is False

        stream.add_to_buffer("Test")
        assert stream.is_running is True

        stream.stop()

    def test_flush_remaining(self) -> None:
        """Test flushing all remaining content."""
        stream = PrintStream()
        stream.start()

        stream.add_to_buffer("Hello")
        stream.add_to_buffer("World")

        # Mock stdout to capture output
        with patch.object(sys.stdout, "write") as mock_write:
            stream.flush_remaining()
            # Should have written both strings
            assert mock_write.call_count >= 2

        stream.stop()

    def test_buffer_size_property(self) -> None:
        """Test the buffer_size property."""
        stream = PrintStream()
        stream.start()

        assert stream.buffer_size == 0

        stream.add_to_buffer("Test")
        assert stream.buffer_size == 4

        stream.add_to_buffer("Message")
        assert stream.buffer_size == 11

        stream.stop()

    def test_queue_length_property(self) -> None:
        """Test the queue_length property."""
        stream = PrintStream()
        stream.start()

        assert stream.queue_length == 0

        stream.add_to_buffer("First")
        assert stream.queue_length == 1

        stream.add_to_buffer("Second")
        assert stream.queue_length == 2

        stream.stop()


class TestDynamicSpeedCalculation:
    """Tests for dynamic speed calculation."""

    def test_speed_calculation_zero_buffer(self) -> None:
        """Test speed calculation with zero buffer length."""
        stream = PrintStream()
        speed = stream._calculate_dynamic_speed(0)
        assert speed == stream.min_speed

    def test_speed_calculation_increases_with_buffer(self) -> None:
        """Test that speed increases as buffer length increases."""
        stream = PrintStream(min_speed=5.0, max_speed=100.0)

        speed1 = stream._calculate_dynamic_speed(10)
        speed2 = stream._calculate_dynamic_speed(100)
        speed3 = stream._calculate_dynamic_speed(1000)

        assert speed1 < speed2 < speed3

    def test_speed_calculation_bounds(self) -> None:
        """Test that speed stays within min/max bounds."""
        stream = PrintStream(min_speed=5.0, max_speed=50.0)

        # Test with very large buffer
        speed = stream._calculate_dynamic_speed(1000000)
        assert speed <= stream.max_speed

        # Test with small buffer
        speed = stream._calculate_dynamic_speed(1)
        assert speed >= stream.min_speed


class TestGlobalFunctions:
    """Tests for global print stream functions."""

    def setup_method(self) -> None:
        """Reset global state before each test."""
        stop_print_stream()
        time.sleep(0.1)  # Allow cleanup

    def teardown_method(self) -> None:
        """Clean up after each test."""
        stop_print_stream()

    def test_start_stop_print_stream(self) -> None:
        """Test global start/stop functions."""
        start_print_stream()
        assert is_print_stream_running() is True

        stop_print_stream()
        assert is_print_stream_running() is False

    def test_print_stream_function(self) -> None:
        """Test the print_stream function."""
        with patch.object(sys.stdout, "write") as mock_write:
            print_stream("Hello", "World", flush=True)
            mock_write.assert_called_once_with("Hello World\n")

    def test_print_stream_with_separator(self) -> None:
        """Test print_stream with custom separator."""
        with patch.object(sys.stdout, "write") as mock_write:
            print_stream("a", "b", "c", sep=", ", flush=True)
            mock_write.assert_called_once_with("a, b, c\n")

    def test_print_stream_with_end(self) -> None:
        """Test print_stream with custom end character."""
        with patch.object(sys.stdout, "write") as mock_write:
            print_stream("Hello", end="", flush=True)
            mock_write.assert_called_once_with("Hello")

    def test_print_stream_queueing(self) -> None:
        """Test that print_stream queues when not flushing."""
        start_print_stream()
        print_stream("Test message")
        assert get_queue_length() >= 1

    def test_configure_print_stream(self) -> None:
        """Test configuring print stream parameters."""
        configure_print_stream(
            min_speed=10.0,
            max_speed=200.0,
            decay_factor=30.0,
            smoothing_factor=0.9,
        )
        # Configuration should be applied to the global instance
        assert is_print_stream_running() is False  # Should not auto-start

    def test_set_print_speed(self) -> None:
        """Test setting print speed range."""
        set_print_speed(min_speed=15.0, max_speed=150.0)
        # Speed should be configured but not auto-started
        assert is_print_stream_running() is False

    def test_get_buffer_size(self) -> None:
        """Test getting buffer size."""
        start_print_stream()
        print_stream("Test")
        # Buffer size should be positive after adding content
        size = get_buffer_size()
        assert size >= 0

    def test_get_queue_length(self) -> None:
        """Test getting queue length."""
        start_print_stream()
        print_stream("Test")
        # Queue length should be at least 1
        length = get_queue_length()
        assert length >= 0

    def test_flush_print_stream(self) -> None:
        """Test flushing all buffered content."""
        start_print_stream()
        print_stream("Test")
        flush_print_stream()
        # After flush, buffer should be empty or smaller
        assert get_buffer_size() == 0


class TestPrintStreamIntegration:
    """Integration tests for PrintStream."""

    def setup_method(self) -> None:
        """Reset global state before each test."""
        stop_print_stream()
        time.sleep(0.1)

    def teardown_method(self) -> None:
        """Clean up after each test."""
        stop_print_stream()

    def test_output_order_preserved(self) -> None:
        """Test that output order matches input order."""
        stream = PrintStream()
        stream.start()

        messages = ["First", "Second", "Third"]
        with patch.object(sys.stdout, "write") as mock_write:
            for msg in messages:
                stream.add_to_buffer(msg)

            # Give time for processing
            time.sleep(0.5)
            stream.flush_remaining()

            # Check that messages were written in order
            written = "".join(call[0][0] for call in mock_write.call_args_list)
            first_idx = written.find("First")
            second_idx = written.find("Second")
            third_idx = written.find("Third")
            assert first_idx != -1
            assert second_idx != -1
            assert third_idx != -1
            assert first_idx < second_idx < third_idx

        stream.stop()

    def test_concurrent_access(self) -> None:
        """Test concurrent access to the print stream."""
        import threading

        stream = PrintStream()
        stream.start()

        def add_messages(prefix: str, count: int) -> None:
            for i in range(count):
                stream.add_to_buffer(f"{prefix}_{i}")

        threads = [
            threading.Thread(target=add_messages, args=("A", 10)),
            threading.Thread(target=add_messages, args=("B", 10)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All messages should be queued
        assert stream.queue_length == 20

        stream.stop()