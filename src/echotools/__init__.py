from __future__ import annotations

"""echotools：通用基础设施 SDK。

完全项目无关，支持调用链，覆盖 Python 3.8-3.14。
"""

from echotools.cache import ListCache, MemoryCache
from echotools.config import ConfigBase, ConfigCenter
from echotools.dispatch import (
    AdaptiveSelector,
    ProxyRecord,
    ProxySelector,
    TaskCandidate,
    TaskDispatcher,
    make_id,
)
from echotools.errors import (
    ConfigError,
    EchoError,
    NetworkError,
    NoCandidateError,
    NotSupportedError,
    PluginError,
    ProtocolError,
    TimeoutError,
    ValidationError,
    classify_http_error,
)
from echotools.events import Event, EventBus
from echotools.files import FileUtil
from echotools.ids import short_id, span_id, trace_id, uuid7
from echotools.io import (
    atomic_write_text,
    ensure_directory,
    read_text_if_exists,
)
from echotools.keys import KeyPool, KeyState
from echotools.lifecycle import AutoUpdater, LifecycleManager
from echotools.logger import LoggerManager, configure, get_logger, set_color
from echotools.plugin import Plugin, PluginRegistry, discover_plugins
from echotools.process import PortReleaseResult, ensure_port_available
from echotools.protocol.base import (
    ToolProtocol,
    get_protocol_by_id,
    list_protocols,
    register_protocol,
)
from echotools.proxy import ProxyManager
from echotools.retry import (
    retry_async_generator,
    retry_on_empty,
    retry_on_exception,
    retry_with_backoff,
)
from echotools.runtime import RuntimeCollector
from echotools.scheduler import TaskScheduler
from echotools.sdk import EchoTools
from echotools.tracing import (
    Span,
    Trace,
    Tracer,
    get_current_span_id,
    get_current_trace_id,
    get_request_id,
    set_current_span_id,
    set_current_trace_id,
    set_request_id,
)
from echotools.terminal import (
    LocalTerminal,
    SSHTerminal,
    TerminalCallback,
    TerminalSession,
)
from echotools.translate import (
    extract_text_from_messages,
    format_translation_response,
    split_text_chunks,
)
from echotools.web import WebApplication, json_body, safe_flush

__version__ = "1.0.26"

__all__ = [
    "__version__",
    # SDK 门面
    "EchoTools",
    # 配置
    "ConfigBase",
    "ConfigCenter",
    # 日志
    "LoggerManager",
    "get_logger",
    "set_color",
    "configure",
    # 事件
    "Event",
    "EventBus",
    # 调用链
    "Tracer",
    "Trace",
    "Span",
    "get_current_trace_id",
    "set_current_trace_id",
    "get_current_span_id",
    "set_current_span_id",
    "get_request_id",
    "set_request_id",
    # 缓存
    "ListCache",
    "MemoryCache",
    # 调度
    "TaskCandidate",
    "make_id",
    "AdaptiveSelector",
    "TaskDispatcher",
    "TaskScheduler",
    # 代理选择
    "ProxySelector",
    "ProxyRecord",
    # 插件
    "Plugin",
    "PluginRegistry",
    "discover_plugins",
    # 协议
    "ToolProtocol",
    "register_protocol",
    "get_protocol_by_id",
    "list_protocols",
    # 生命周期
    "LifecycleManager",
    "AutoUpdater",
    # 网络/代理/进程
    "ProxyManager",
    "PortReleaseResult",
    "ensure_port_available",
    # 运行时
    "RuntimeCollector",
    # Web
    "WebApplication",
    "json_body",
    "safe_flush",
    # 工具
    "FileUtil",
    "uuid7",
    "short_id",
    "trace_id",
    "span_id",
    "atomic_write_text",
    "ensure_directory",
    "read_text_if_exists",
    "retry_with_backoff",
    "retry_on_empty",
    "retry_on_exception",
    "retry_async_generator",
    # Key 管理
    "KeyState",
    "KeyPool",
    # 翻译
    "extract_text_from_messages",
    "split_text_chunks",
    "format_translation_response",
    # 终端
    "TerminalSession",
    "TerminalCallback",
    "LocalTerminal",
    "SSHTerminal",
    # 错误
    "EchoError",
    "ConfigError",
    "ValidationError",
    "NetworkError",
    "TimeoutError",
    "NotSupportedError",
    "NoCandidateError",
    "PluginError",
    "ProtocolError",
    "classify_http_error",
]
