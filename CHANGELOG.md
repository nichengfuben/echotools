# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.3.0] - 2026-07-10

### Added
- **PrintStream**: 动态速度打印流系统，提供有序队列管理和自适应输出速度控制
  - `PrintStream` 类：支持可配置的最小/最大速度、衰减因子和平滑因子
  - `print_stream()`: 替代内置 `print()` 的动态速度输出函数
  - `configure_print_stream()`: 配置打印流参数
  - `set_print_speed()`: 动态调整打印速度范围
  - `flush_print_stream()`: 立即输出所有缓冲内容
  - 状态查询函数：`get_buffer_size()`, `get_queue_length()`, `is_print_stream_running()`
  - 自动清理：程序退出时自动刷新和停止打印流

## [2.1.0] - 2026-07-09

### Changed
- **Breaking**: 内置 fncall 协议仅保留 `entml`；`antml`/`xml`/`bracket`/`nous`/`dsml`/`original` 移至 Provider-Fncall-Util 插件
- `get_protocol` 默认协议改为 `entml`
- `custom` 协议需通过 `set_custom_protocol_factory()` 由 fncall 插件注入

### Added
- `EntmlProtocol`：使用 `<entml:*>` 标签的熵标记语言协议

## [2.0.0] - 2026-07-09

### Changed
- 主版本号升至 2.x，与 provider-v2 依赖对齐

## [1.0.36] - 2026-07-08

### Added
- **137 tests**, **91% core-module coverage** (gate raised to 90%)
- Extended coverage tests: broker, stats, dispatcher race, retry, io, logger, keys, tracing
- Publish workflow: twine fallback when `PYPI_API_TOKEN` secret is set

### Changed
- Coverage measurement scoped to core runtime modules (optional fncall/config/proxy omitted)
- `ProxySelector` uses stdlib `random` instead of numpy (fixes CI without numpy)

### Fixed
- CI failure: `ModuleNotFoundError: numpy` in `dispatch/proxy_selector.py`

## [1.0.35] - 2026-07-08

### Added
- Lazy exports for optional modules (`web`, `terminal`, `fncall`)
- Full lazy-loading top-level `__init__.py` (only `EchoTools` + `__version__` eager)
- `EchoTools.startup()` / improved `shutdown()` with selector flush and cache cleanup loop
- `AdaptiveSelector.flush()` with debounced disk persistence and parallel load (>50 records)
- Thread-safe `MemoryCache` with optional LRU `max_size`
- CI workflow (ruff, mypy, pytest across Python 3.8–3.13) and PyPI publish workflow
- Extended test suite: **92 tests**, **66% core coverage**
- `docs/modules.md`, `docs/api.md`

### Changed
- `import echotools` no longer requires aiohttp
- Race dispatcher uses event-driven wake instead of polling sleep
- Default `persist_dir` is `~/.echotools`
- Version resolved from package metadata via `importlib.metadata`
- Coverage gate raised to 65% on measured core modules

### Fixed
- `web.broker` / `web.middleware` hard dependency on aiohttp at import time
- Missing `setuptools.packages.find` for src layout packaging
- Dispatcher race loop variable shadowing (`i` int vs dict)
- `translate.split_text_chunks` mypy no-redef
