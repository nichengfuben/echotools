# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
