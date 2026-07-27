# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.3.52] - 2026-07-28

### Fixed

- 流式 partial_json：invoke ready 后对齐 encoder 已发快照，避免下一 chunk 重发整段 JSON（`Extra data` 导致 Bash 等工具循环失败）

## [2.3.51] - 2026-07-28

### Fixed

- 流式 thinking 内完整 `<entml:invoke>` 块现可切出并解析（含 `</entml:thinking>` 前/未闭合 thinking 内真实 invoke；占位符 `$FUNCTION_NAME` 仍忽略）
- fault ``</thinking>`` 后 invoke 开标签完整匹配时清除 fault_watch，后续 parameter 分片不再误入 thinking 路径
- 多 invoke / invoke 闭合后可见正文：不再过早 ``DONE``，避免并行工具或 trailing 文本丢失
- 流式 partial_json：invoke 闭合前先 poll 再转态，避免缺少尾部 ``}``

## [2.3.50] - 2026-07-28

### Fixed

- 流式解析：首包含 thinking 内 invoke 开标签时不再误进 `IN_FUNCTION_CALLS`（`invoke_index_inside_unclosed_thinking`）
- fault ``</thinking>`` 后 invoke 与 ``<entml:parameter>`` 分片时 holdback ``<ent`` 并入 fncall 缓冲，避免参数解析为 ``{}``
- prompt 构建：移除 assistant 消息去重（重复 assistant 全部保留进历史）

### Added

- `test_entml_parser_comprehensive.py` / `test_entml_agent_output_formats.py` 全方位解析与边界回归

## [2.3.49] - 2026-07-28

### Fixed

- thinking 块：仅 ``</entml:thinking>`` 闭合后才解析工具；块内 ``<entml:`` 一律视为思考文本
- 容错 ``</thinking>``：仅当其后出现完整 ``<entml:invoke`` 开标签时才提前结束思考；否则直到 ``</entml:thinking>`` 仍作纯文本

## [2.3.48] - 2026-07-28

### Fixed

- entml 流式 `input_json_delta`：多参数 invoke 时不再在中间参数完成后提前闭合 `}`，修复 delta 拼接 Extra data

## [2.3.47] - 2026-07-28

### Fixed

- entml 流式：invoke 开标签就绪后增量输出 `input_json_delta`（`EntmlInvokeJsonStreamEncoder`），避免长 parameter 期间 SSE 静默
- thinking 块内出现 `<entml:invoke` 等工具前缀时 holdback/切出，避免 invoke 被 thinking 吞掉
- 无 tools 的 inject 路径渲染 `<user_system_prompt>` 块
- 无 tools 时 `thinking_behavior` 不再提及 `<entml:invoke>`

## [2.3.46] - 2026-07-27

### Fixed

- entml 流式检测对齐裸 `<entml:invoke>` 提示词：`function_calls` 不再参与 trigger/holdback；legacy 外壳流式静默剥离
- 新增裸 invoke 全方位测试套件（740 tests）

### Changed

- 拆分 `media.console.ui` 为 `uicore` / `uilayout` / `uiwidgets` 模块；修复拆分后 ruff/mypy 问题

## [2.3.40] - 2026-07-27

### Fixed

- 流式解析：未闭合 `<entml:thinking>` 期间块内按纯文本处理，不检测/解析 `<entml:invoke>` 等标签；闭合后才进入正常 fncall 检测
- `has_unclosed_entml_thinking` / `EntmlThinkingStreamFilter.in_open_thinking()` 供 stream parser 与测试使用

## [2.3.39] - 2026-07-27

### Fixed

- `prompt_helpers`: assistant history f-string compatible with Python 3.8–3.11 (fixes import SyntaxError on CI)
- Lint: ruff import order / unused imports; console `ui.py` mypy override

## [2.3.22] - 2026-07-22

### Added

- `entml_thinking_history`：`parse_interleaved_history()`、`apply_thinking_history_policy()`、`extract_reasoning_text()`
- 支持 Entropy/Anthropic 内容块（`type: thinking`）的历史交错开关：开则保留思考+回复，关则仅保留可见回复

## [2.3.21] - 2026-07-22

### Changed

- 新增 `parse_max_thinking_length()`：未显式传入正整数时不注入 `<entml:max_thinking_length>`
- `thinking_mode=off` 时仍不注入任何 thinking 相关标签

## [2.3.20] - 2026-07-22

### Changed

- `thinking_mode=off` 时不再向 prompt 注入任何 thinking 标签或引导文案（含 `max_thinking_length`）

## [2.3.19] - 2026-07-22

### Added

- `normalize_thinking_mode()`：归一化为 `off` | `on` | `auto`
- 三套 prompt：`off` 强制不思考、`on` 强制思考、`auto` 自动思考（含工具结果后示例）
- 无 tools 的 entml 注入路径也会附带 thinking 指令块

### Changed

- `adaptive` / `interleaved` 别名映射到 `auto`（非独立 mode）

## [2.3.18] - 2026-07-22

### Changed

- 强化 off/on/auto 三套 thinking prompt：含模式说明、MUST/NOT 规则与示例
- 无 tools 的 entml 注入路径也会附带 thinking 指令块

## [2.3.17] - 2026-07-22

### Added

- `normalize_thinking_mode()`：归一化思考模式为 `off` | `on` | `auto`
- 三套 prompt：`off` 强制不思考、`on` 强制思考、`auto` 自动思考

### Changed

- `build_entml_thinking_section()` 按模式输出不同指令文案

## [2.3.16] - 2026-07-22

### Added

- `entml_thinking_parse`：解析/流式拆分 `<entml:thinking>` 块

### Changed

- thinking 说明改回 “At the very start of your response...”

## [2.3.15] - 2026-07-22

### Fixed

- 回滚 2.3.14 误改的 thinking 标签与文案，仅保留 `<current_user_message>` 开闭标签调整

## [2.3.14] - 2026-07-22

### Changed

- entml `<current_user_message>` / `</current_user_message>` 开闭标签统一（去掉 `entml:` 前缀）
- thinking 示范与说明改为 `<thinking>` `</thinking>`，并更新为 “At the very start of your response...” 文案

## [2.3.13] - 2026-07-22

### Fixed

- entml 解析：`<entml:parameter>` 支持 `type="str"` 等额外属性；无 `type=` 时标量默认按 `str` 处理

### Changed

- entml 工具块 JSON Schema 自动排版（字段排序、多行 description 展开）
- `</entml:current_user_message>` 闭标签改为 `</current_user_message>`

## [2.3.12] - 2026-07-22

### Changed

- entml prompt 对齐 antml 示范：环境说明 + `**name**` JSONSchema 工具块；thinking 置于工具列表之后；移除 `<functions>` 包裹

## [2.3.9] - 2026-07-21

### Changed

- 全量 achecker 合规：模块重组为 `base`/`exec`/`media`/`plat` 四层 meta-package，拆分超长文件与函数，重命名 web 静态资源

## [2.3.7] - 2026-07-21

### Added

- `normalize_tool_call` / `normalize_tool_calls`：将 tool call arguments 中的 Python 字面量字符串（如 `"['a','b']"`）还原为合法 JSON 结构；`parse_fncall`、`parse_fncall_xml` 与 `entml` 协议解析出口自动应用

## [2.3.6] - 2026-07-20

### Changed

- `web/input_box` 子模块目录由 kebab-case 重命名为 snake_case（`file_zone/`、`motion_kit/` 等），与 setuptools `package-data` 路径一致，避免部分环境下静态资源打包缺失

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
