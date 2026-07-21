from __future__ import annotations

"""io 模块导出。"""

from echotools.base.io.io_utils import (
    atomic_write_text,
    ensure_directory,
    read_text_if_exists,
)
from echotools.base.io.printstream import (
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

__all__ = [
    "atomic_write_text",
    "ensure_directory",
    "read_text_if_exists",
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
