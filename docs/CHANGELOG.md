# Changelog

本文件记录 [echotools](https://github.com/nichengfuben/echotools) 的所有 notable 变更。
格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，版本号与
[PyPI](https://pypi.org/project/echotools/) / `pyproject.toml` 同步。

## 版本概览

| 主版本 | 要点 |
|--------|------|
| **2.4.3** | 修复 coercion 循环导入导致 entml_think 等模块无法加载 |
| **2.4.2** | entml fakemarkup 全路径、assistant 历史清理、参数原文保留、coerce+validate 分层、多行参数回归 |
| **2.4.1** | entml thinking prompt 恢复 `<entml:thinking>` 显式格式与 on/auto/off 全分支；thinking 约束仅由 `<thinking_behavior>` 承担 |
| **2.4.0** | **Breaking**：移除旧模块路径别名、`custom` 协议工厂、XML 解析器、`<tool>` 块解析、`function_calls` 外壳兼容、主题 `blue` 别名、Write `path`→`file_path` 映射 |
| **2.3.x** | entml 协议持续增强：流式 partial_json、thinking 容错、伪 history 剥离、prompt 块顺序、golden 回归；`media.console` 多主题 UI 桥接 |
| **2.1.0** | **Breaking**：内置 fncall 仅保留 `entml`；`get_protocol` 默认改为 `entml`；其余协议移至 Provider-Fncall-Util 插件 |
| **2.0.0** | 主版本升至 2.x，与 provider-v2 依赖对齐 |
| **1.0.x** | 基础设施 SDK：懒加载、`EchoTools.startup()`、CI/PyPI 发布、核心模块测试覆盖 |

安装与快速示例见仓库根目录 [README.md](../README.md)。

## [Unreleased]

（暂无）

## [2.4.3] - 2026-08-03

### Fixed

- `shared/coercion.py` 顶层 import `entml_schema.validate` 触发 `protocols` 包注册链，造成循环导入；Rogator 等场景加载 `entml_think` 即失败。null union 辅助函数改由 `coercion` 定义，`validate` 单向复用。

## [2.4.2] - 2026-08-03

### Added

- entml schema 校验层（`entml_schema/validate.py`）：enum、null union、基础类型匹配；`ToolArgValidationError.to_llm_feedback()` 供模型自修正
- `coerce_entml_arguments(..., strict=True)` 可选严格校验（默认 soft，兼容既有行为）
- 多行 parameter 全方位回归（`test_multiline_parameter_comprehensive.py`）与 schema validate 单测

### Changed

- entml 解析与 assistant 历史清理统一走 `strip_fake_entml_structure_markup`；空行折叠跳过 `<entml:invoke>` 块以保护 parameter 内换行
- string 参数保留模型原文（不 strip），流式完成态与 batch 对齐
- 删除未使用的 `prompt/templates.py`；`_HISTORY_CLARIFY_EN` 迁入 `shared/entml_format.py`

### Fixed

- fakemarkup 全局 `\n{3,}` 折叠破坏 invoke 内多行 parameter 的问题
- 流式 string 参数 lstrip 导致与 batch 不一致的问题
- null union（`["string","null"]`）在 coerce 阶段正确解析为 `None`

## [2.4.1] - 2026-08-02

### Fixed

- entml `<thinking_behavior>` 恢复显式 `<entml:thinking>...</entml:thinking>` 格式说明（2.3.93 重构后丢失）
- entml thinking 分支恢复 on / auto / off（含 history 有 thinking 时）与 has_tools 分路
- entml `<entml:hard_constraint_restatement>` 不再重复 thinking 约束，避免与 off 模式冲突
- `achecker.py` logger 导入对齐 2.4.0 包布局（`echotools.base.logger`）

## [2.4.0] - 2026-08-02

### Removed

- **Breaking** `echotools.compat` 及 pre-2.3.9 模块路径别名（`echotools.config` 等）
- **Breaking** `set_custom_protocol_factory` / `clear_custom_protocol_factory` 与 `custom` 协议
- **Breaking** `parse_fncall` / `parse_fncall_xml`（XML 协议解析器）
- **Breaking** `<tool>` 块解析（`entml_tool/blocks.py`、`entml_think/blocks.py` 重复实现）
- **Breaking** `strip_legacy_function_calls_wrapper` 与 `function_calls` 开闭标签静默剥离
- **Breaking** 主题名 `blue` / `default` → `ocean` 别名
- **Breaking** Write 工具 `path` → `file_path` 参数名映射

### Changed

- entml 流式/批解析统一为裸 `<entml:invoke>` 一等格式
- `media.console` 仅接受 `THEME_PRESETS` 内主题名

## [2.3.104] - 2026-08-01

### Fixed

- entml thinking 行为块移除默认回复语言强制（Simplified Chinese / switch languages）

## [2.3.103] - 2026-08-01

### Added

- entml golden 回归：`fixtures/entml_golden.json` 锁定 32 条语料的 `parse()` 输出与 `build_streaming_json_snapshot()` 快照；`test_entml_golden.py` 校验 digest 与逐 case 等价

### Fixed

- `render_gradient_banner` 改为输出真 ANSI 渐变（`render_banner_ansi`），避免 `str(Rich.Text)` / `NO_COLOR` 导致横幅无色
- entml thinking 行为块移除“末行声明回复语言”硬约束

## [2.3.102] - 2026-08-01

### Changed

- `media.console` UI 桥接层改为通用多主题：`RichCLI` + `ui_themes` 预设（ocean/forest/sunset/violet/rose/slate/cyan）；移除 Blue 专用命名与 `BlueCLI`
- 旧配置值 `blue` 自动映射为 `ocean`

## [2.3.101] - 2026-08-01

### Added

- `media.console` 新增 `uilayout/ui_bridge.py`：同步 `run_select`/`run_confirm`、`create_themed_ui`、蓝色渐变主题、ASCII 横幅渲染、配置 flatten/coerce、`render_bar`/`truncate_ansi`
- `media.console` 新增 `uiwidgets/ui_blue_cli.py`：`BlueCLI`、Rich 蓝色主题与 `get_console` 工厂

## [2.3.99] - 2026-07-30

### Fixed

- entml 输出过滤：``<entml:todo>`` / ``</entml:todo>`` 仅剥标签、保留正文
- entml 输出过滤：invoke 块移除后剥离独立行/文末孤儿 ``</entml:…>`` 闭标签（如多余 ``</entml:invoke>``）

## [2.3.98] - 2026-07-30

### Fixed

- entml 输出过滤 Step 2：仅剥标签，保留正文 — 新增 ``<entml:call>`` / ``</entml:call>``

## [2.3.97] - 2026-07-30

### Fixed

- entml 输出过滤：剥离模型误生成的残缺闭标签 ``</entml:`` / 单行 ``● </entml:…``（invoke 解析后的可见区尾部）

## [2.3.96] - 2026-07-30

### Fixed

- entml 输出过滤两步分离：**Step 1** 带 ``id`` 的 ``<entml:result id="…">…</entml:result>`` 整块剥离（含内部正文；流式未闭合 hold）；**Step 2** 仅剥离开/闭标签本身（``>`` 闭合即滤，保留标签间/后正文）：``funtions_results`` / ``conversation_history`` / ``entml:calls`` / ``function_calling_behavior`` / ``thinking_behavior`` / 无 id 的 ``entml:result``

## [2.3.95] - 2026-07-30

### Added

- entml 输出过滤：自动剥离模型误生成的 ``<!-- Tool Result ID:… -->``（完整 ``-->`` 闭合后移除；流式未闭合 hold）
- entml 输出过滤：剥离伪 ``<entml:result>`` / ``<entml:funtions_results>`` / ``<entml:conversation_history>`` 开闭标签（``>`` 闭合即滤；result 正文在 ``</entml:result>`` 收齐前不可见）

## [2.3.94] - 2026-07-30

### Fixed

- entml prompt 块顺序：``conversation_history`` → ``funtions_results`` → ``function_calling_behavior`` → ``thinking_behavior`` → ``hard_constraint_restatement`` → ``current_user_message`` → thinking 元数据

## [2.3.93] - 2026-07-30

### Changed

- entml history / prompt：工具结果与 history 分离（``funtions_results`` + id 注释）；行为块与 instruction 对齐新架构

## [2.3.92] - 2026-07-29

### Changed

- entml prompt：移除末尾 ``IMPORTANT — Tool invocation format`` 块；有 tools 时在 ``<current_user_message>`` 之后注入 ``<function_calling_behavior>``；尾部顺序为 ``thinking_behavior`` → ``max_thinking_length`` → ``thinking_mode``（``thinking_mode`` 置末以便截断保留）
- entml history：assistant 轮次内 invoke 后仅环境回填 ``<!-- Tool Result ID:{id} -->``；累计 ``<entml:result id="...">`` 写入顶层 ``<entml:funtions_results>``（与 history 平级）
- entml prompt 顺序：工具说明 → ``conversation_history`` → ``funtions_results`` → ``function_calling_behavior`` → ``thinking_behavior`` → ``hard_constraint_restatement`` → ``current_user_message`` → thinking 元数据
- entml 解析：移除 ``<tool>`` / ``{ToolName: …}`` 作为 ``tool_calls`` 的解析路径（保留伪 history 块剥离防御）；仅 ``<entml:invoke>`` 闭合且 ``name`` 在已知 tools 内才解析

## [2.3.91] - 2026-07-29

### Changed

- entml 末尾 IMPORTANT 硬约束块按 System Prompt Authoring Specification 重写：每条规则以 ``IMPORTANT:`` 开头、首尾 verbatim 复述、含 guard 示例块；工具调用表述改为 ``If you execute a tool in this turn`` 条件句式，不再暗示每轮必须调工具

## [2.3.90] - 2026-07-29

### Changed

- entml 有 tools 时在 prompt 末尾（``<current_user_message>`` 之后、thinking 之前）追加加强版 ``IMPORTANT — Tool invocation format`` 块，再次强调闭合 ``<entml:invoke name="…">``、已知工具名、parameter 格式及勿复用 history ``<tool>`` 记号

## [2.3.89] - 2026-07-29

### Fixed

- entml invoke 解析/过滤：仅当 ``<entml:invoke …>`` 已闭合 ``>`` 且 ``name`` 在已知 tools 列表内时才进入工具流、剥离或 batch 解析；保留 prose ``<entml:invoke>`` 提及与未知工具名 invoke
- entml 流式 ``partial_text``：仅在 actionable invoke 起点截断；未闭合 invoke 尾部 hold；带属性的工具标签剥离时不误伤无 name 的 prose 提及

### Added

- ``resolve_known_tool_names`` / ``find_actionable_entml_invoke_open`` 及 ``test_entml_invoke_known_tool_gate`` 全方位回归（batch + 多 chunk 流式）

## [2.3.88] - 2026-07-29

### Fixed

- entml invoke 解析：整段 ``<entml:parameter>`` 块视为不透明 payload，备用语法（直接子标签 / description / timeout）仅在 structural gap 解析，避免 Write 等内容参数内嵌 HTML/Vue 标签（如 ``<span>``、``<slot>``）泄漏为额外工具参数（req-1785323083）
- entml parameter 闭标签 follower：invoke 级直接子元素（``<path>``、``<-n>`` 等）视为合法兄弟节点，修复 parameter + 直接子标签混合格式边界误判

### Added

- structural gap 辅助函数（``parameter_block_spans`` / ``invoke_structural_gap_text``）及 mixed-syntax、语料回归测试

## [2.3.87] - 2026-07-29

### Fixed

- entml Write ``content``/``path`` 等大字段参数跳过 mangled Bash 尾缀启发式，避免内嵌 JSON 示例（如 ``", "type"``）被误截断（req-1785314805）
- entml mangled 尾缀：``", "description"`` 紧跟 command 闭合引号时在首段截断，流式 partial_json 与 batch 一致
- entml fault thinking：``</thinking>`` 后允许可见正文再跟 ``<tool>``/invoke，不再把整段响应当作未闭合 thinking
- entml ``<tool>`` 块：支持 ``{Write: {"path","content":...`` + ``</content>`` 混合格式；``path`` 映射 ``file_path``

### Changed

- fncall/entml 模块拆分以通过 achecker（``entml_stream`` 包、``entml_schema``、stream mixins、thinking hold/filter）

### Added

- 三条 Qwen 语料回归：req-1785314805 / req-1785311004 / req-1785314760

## [2.3.86] - 2026-07-29

### Fixed

- entml 流式 partial_json：bare ``description``/``timeout`` 未闭合时去掉尾部 ``</entml:…>`` 片段，避免 snapshot 回缩导致 6537 字节非法 JSON（大 Bash req-1785309429）
- entml ``<tool>`` 块：支持 ``{Read}`` + ``<entml:parameter>`` 混合格式（除既有 ``{Bash>`` 外）
- entml fault thinking：``</thinking>`` 后若紧跟 ``<tool>``/``<entml:invoke>``，中间中文视为可见正文而非思考链；``split_entml_thinking`` 不再泄漏 ``</entml:thinking>`` 到 clean
- entml 流式 ``finalize``：batch thinking 非空时用其校正 ``partial_thinking``

### Added

- ``test_large_bash_bare_description_stream_parity``、``test_entml_tool_block_brace_read_entml_params`` 语料回归

## [2.3.85] - 2026-07-29

### Fixed

- entml user 消息：``strip_entml_from_content`` 仅去掉 ``entml:`` 标签前缀，保留标签结构与 ``//`` 路径
- entml 流式：thinking 块内 ``<entml:invoke>`` 示例不再误触发工具解析截断
- history markup：orphan ``</assistant>`` 等闭标签只删标签行，不再吞掉前文可见正文

## [2.3.84] - 2026-07-29

### Fixed

- entml invoke 剥离/解析：仅匹配开标签含真实 ``name`` 的 ``<entml:invoke>…</entml:invoke>``；正文 prose ``<entml:invoke>`` 提及不再吞掉后续真实工具块（req-1785299710）
- entml ``split_mangled_json_param_tail``：JSON 数组/对象参数内的 ``description`` 等字段不再误触发 Bash command 尾缀截断（AskUserQuestion req-1785299204）
- entml 参数类型：``parameter type`` 优先、否则 schema；batch/stream 共用 ``coerce_entml_parameter_value`` / ``effective_entml_param_json_type``
- schema ``array``：单对象 JSON 值自动包装为单元素数组（AskUserQuestion 单 parameter 对象）

### Added

- ``test_prose_entml_invoke_mention_does_not_swallow_real_invoke``、``test_ask_user_question_array_param_not_split_on_description_key`` 语料回归

## [2.3.83] - 2026-07-29

### Fixed

- entml 流式 ``partial_text``：thinking 闭合后不再把思考正文重复泄漏到 answer（``stream_safe_visible_prefix`` / ``clean_stream_partial_visible`` 顺序修正）
- entml batch/stream Bash：未闭合 ``<entml:parameter>`` + 误写入 command 的 JSON 尾缀（``", "description": ..., "timeout": ...}}``）可正确解析；流式 ``json_buf`` 不再出现 1596 字节非法 JSON
- entml 流式 partial_json：快照回退时不发 append-only 错误 delta；invoke ready 时 diverged tail 不再追加垃圾后缀
- entml ``<tool>`` 块：支持 ``{Bash>`` + ``<entml:parameter>`` 混合格式（req-1785297403）

### Added

- ``test_thinking_close_does_not_leak_into_partial_text``、``test_mangled_json_tail_in_command_param_batch_and_stream`` 语料回归
- ``test_entml_tool_block_mangled_brace_entml_params``：``<tool>{Bash>`` 混合格式 batch/stream
- ``test_entml_tool_block_mangled_brace_entml_params``：``<tool>{Bash>`` + ``<entml:parameter>`` 混合格式

## [2.3.82] - 2026-07-29

### Fixed

- entml 流式 partial_json：``anyOf``/``oneOf`` schema 的 integer 参数（如 Read ``line_offset``）不再误按 string 加引号，修复 Rogator ANT/OAI 流式 ``json_buf`` 出现 ``143143`` 等非法 JSON

### Added

- ``test_read_anyof_integer_stream_json_buf_matches_batch``：Read + anyOf integer 流式/batch parity 回归

## [2.3.81] - 2026-07-29

### Fixed

- entml 流式 ``partial_text``：改从 raw 缓冲在 invoke 前截断推导，修复 char-by-char 分片丢失换行导致 orphan ``</assistant>`` 泄漏
- entml 流式 ``partial_text``：invoke 开标签 holdback 时保留尾部空白（``hello <entml:inv`` → ``hello ``）
- entml 流式 partial_json：裸 ``</parameter>`` 在 buffer 末尾时可正确闭合（req-1785261134 parity）
- entml 流式 ``partial_text`` / thinking 边界：修复 thinking 结束后 orphan ``</entml:thinking>``、``<`` 前缀泄漏（req-1785260732）
- entml 伪 history 流式展示：``glued_open`` / ``partial_fake_close`` 仅匹配行首，保留正文内 ``<tool>`` 提及

### Added

- ``test_entml_batch_stream_comprehensive``：req-1785260732 / req-1785261134 回归
- ``test_stream_partial_json_parity``：bare ``</parameter>`` buffer 末尾 snapshot 测试

## [2.3.80] - 2026-07-29

### Fixed

- entml 流式 ``partial_text``：未收齐的 ``<entml:thinking`` / invoke 开标签前缀不再泄漏为可见 ``<``
- entml ``<tool>`` 容错：支持 ``{Read: path}`` 标量行、``</system>`` 误闭合及 Read 输出 tail；解析后剥离 mimic 块并保留 ``</assistant>`` 之后正文
- entml batch ``parse()``：先剥离 thinking / 已解析 tool 块，再剥离伪 history，避免真实回复被整段清空

## [2.3.79] - 2026-07-29

### Fixed

- entml batch ``parse()``：thinking 剥离移至 invoke 移除之前，修复 fault ``</thinking>`` 语料泄漏 ``<entml:thinking>`` 标签；返回可见正文不再含 entml 标签

### Added

- ``test_entml_batch_stream_comprehensive``：模拟语料 / fault thinking / 伪 history / Qwen 真实日志语料的全方位 batch+stream parity 与标签泄漏回归（多 chunk 分片）

## [2.3.78] - 2026-07-29

### Fixed

- entml 流式 ``get_ready_tool_calls``：增量解析跳过 ``<tool>`` brace 块，避免 history 伪块在 ``<entml:invoke>`` 到达前误触发（与 batch ``allow_brace=False`` 对齐）
- entml 流式 ``finalize``：有 tool call 时仍剥离 ``<entml:thinking>``，修复 fault ``</thinking>`` 语料可见正文泄漏
- entml 流式 partial_json：参数值内尖括号（如 ``docs/<draft>.md``）不再被 direct-child 解析误拆为额外字段
- entml 流式 ``partial_text``：invoke 前缀 holdback（``_waiting_tail``）不再泄漏到可见正文

## [2.3.77] - 2026-07-29

### Added

- entml ``<tool>...</tool>`` 容错：支持 ``<ToolName>{json}</ToolName>`` / ``<ToolName>…</tool>`` 及单行 ``{Tool: {...}}`` 解析为 tool_calls（thinking 区内不解析；同文已有 ``<entml:invoke>`` 时不解析 brace 伪块；多 brace / 带结果 tail 仍视为 history）

### Fixed

- 流式 ``finalize`` 在无 tool call 时对 ``partial_text``/返回值补做 ``strip_tool_entml_residue``，避免 orphan ``entml:`` 标签泄漏

## [2.3.76] - 2026-07-28

### Fixed

- entml 流式 ``finalize`` / ``partial_text``：在含多段 ``<entml:thinking>`` 与伪 ``<assistant>``/``<tool>`` 的回复上，改为基于 ``_raw_buf`` 剥离伪 history（保留 thinking 保护区），修复可见正文被整段清空、只剩 thinking 的问题

### Added

- ``test_entml_stream_multi_thinking_fake_history_visible_reply``

## [2.3.75] - 2026-07-28

### Fixed

- entml 批量/流式：支持 invoke 内直接子元素 ``<pattern>v</pattern>`` / ``<-n>true</-n>``（标签名即参数名，无 parameter 包裹）

### Removed

- entml 参数名归一容错：不再将 ``file_path`` / ``filepath`` 自动映射为 ``path``（参数名按模型输出原样解析）

### Added

- ``test_entml_parse_direct_child_tags_grep``：req-1785250814 语料 batch + 流式 parity
- ``test_entml_parse_read_file_path_not_aliased``：确认不做参数名映射

## [2.3.74] - 2026-07-28

### Fixed

- entml 参数名归一：模型输出 ``file_path`` / ``filepath`` 时，若 schema 要求 ``path`` 则自动映射

### Added

- ``test_entml_parse_read_file_path_alias``

## [2.3.73] - 2026-07-28

### Fixed

- entml 批量/流式：支持 invoke 内裸 ``<parameter name="...">``（无 ``entml:`` 前缀），修复 arguments 为空导致工具 required 校验失败

### Added

- ``test_entml_parse_bare_parameter_tags_in_invoke``：Edit 语料 batch + 多 chunk 流式 parity

## [2.3.72] - 2026-07-28

### Fixed

- entml 批量/流式解析：支持 invoke 内裸 ``<entml:description>`` / ``<entml:timeout>`` 子标签（非 parameter 包裹）
- ``PARAM_RE`` 闭合 lookahead 允许 description/timeout 等 invoke 兄弟节点，避免参数值截断导致 ``arguments: {}``
- 流式 delta 按 invoke slot 分队列，同名连续多 invoke 不再拼成一条 JSON

### Added

- ``stream_invoke_argument_snapshots()``：各 invoke slot 流式 arguments 快照
- ``test_entml_parse_bare_description_timeout_tags``、``test_entml_stream_same_tool_name_multiple_invokes``

## [2.3.71] - 2026-07-28

### Fixed

- batch ``protocol.parse`` 须在移除 ``<entml:invoke>`` **之前**剥离伪 history，避免未闭合 ``<tool>`` 在二次 strip 时吞掉 invoke 之后的可见回复
- 伪 history 保护区扩展至 ``<entml:function_calls>`` 包裹块；流式 ``partial_text`` 对未闭合 function_calls/invoke 不再截断尾部

### Added

- ``test_fake_history_markup_reply_protect``：invoke + 可见尾句 batch/stream parity、function_calls 包裹、invoke 后伪 tool 等 7+ 语料

## [2.3.70] - 2026-07-28

### Added

- 思考关闭且 ``conversation_history`` 含 ``<entml:thinking>`` 历史块时，注入强制不思考的 ``<thinking_behavior>``（无 ``<entml:thinking_mode>``）；无历史思考时保持不注入

## [2.3.69] - 2026-07-28

### Fixed

- 伪 history 剥离建立 ``<entml:invoke>`` 保护区：未闭合/块内夹 invoke 时不再误删真实工具调用
- 流式 ``_fncall_buf`` 与正文分片时，invoke 前未闭合伪 ``<tool>`` 块正确剥离

### Added

- ``test_fake_history_markup_invoke_preserve`` + 语料 ``unclosed_fake_tool_before_invoke`` 等 3 条

## [2.3.68] - 2026-07-28

### Fixed

- 伪 ``<tool>`` / ``<assistant>`` 成对块：流式分片丢换行时仍可按 ``<tool>\\n…\\n</tool>`` 剥离
- ``partial_text`` 截断 ``</thinking><tool`` 等分片边界粘连的未收齐伪标签

### Added

- 模拟模型伪 history 语料 ``simulated_fake_history_markup_responses``（17 条）
- ``test_fake_history_markup_batch`` / ``test_fake_history_markup_stream`` 全方位 batch/stream/char-by-char/分片回归

## [2.3.67] - 2026-07-28

### Fixed

- 流式 ``partial_text`` 实时剥离伪 ``<assistant>`` / ``<tool>`` 块，不再等到 ``finalize()`` 才从 UI 路径隐藏
- 可见正文中的 orphan ``</thinking>`` 行（无 ``<entml:thinking>`` 开标签）一并移除

## [2.3.66] - 2026-07-28

### Fixed

- 模型误输出块级 ``<assistant>`` / ``<tool>`` 伪 history 标签：batch/stream 解析时剥离（保留 ``<entml:thinking>`` 内讨论）
- 反向闭合 ``</assistant>`` / ``</tool>``（无开标签）及 orphan 开标签块一并移除；行内 prose 提及 ``<tool>`` 不误伤

### Added

- 检测到历史 assistant 消息含伪标签时，注入 ``<history_markup_warning>``（与 ``<loop_warning>`` 同级，位于 ``<current_user_message>`` 前）

## [2.3.65] - 2026-07-28

### Fixed

- 批量 ``parse()``：未闭合 ``<entml:thinking>`` 时 ``clean`` 不再泄露块后正文（与流式一致，仅保留开标签前可见内容）

### Added

- ``</thinking>`` fault 容错专项语料与测试：``test_fault_thinking_close_batch`` / ``test_fault_thinking_close_stream``（模拟 rogator / Claude Code 高发输出）

## [2.3.64] - 2026-07-28

### Fixed

- 未闭合 ``<entml:thinking>`` 块内内容（含 invoke 标记）一律视为思考正文，不解析为工具调用
- 仅三种容错闭合生效：标准 ``</entml:thinking>``、``</thinking>`` 后接 invoke、plain ``<thinking>`` 开标签
- 批量 ``parse()`` 先剥离 thinking 块再解析工具；未开思考时不启用流式 thinking 过滤器

## [2.3.63] - 2026-07-28

### Fixed

- entml 流式 ``partial_json``：参数值内假 ``</entml:parameter>`` 不再截断大 payload；``find_valid_parameter_close`` 结构性感知闭合
- conversation history 工具行格式：多参数/复杂值用 ``{ToolName: json}``，单简单标量用 ``{ToolName: value}``（不再错误输出方括号）
- ``format_entml_parameter_value`` 用于 history 渲染，正确处理多行与嵌套引号

## [2.3.62] - 2026-07-28

### Fixed

- thinking 容错仅在**已开启思考**（``protocol_options`` 注入 thinking 段）时生效；显式 ``off`` / ``none`` 时不识别 plain ``<thinking>`` 开标签与 ``</thinking>`` fault 闭合
- ``FncallStreamParser`` 新增 ``protocol_options`` 参数，流式/批解析与过滤器共享 ``is_thinking_enabled`` 判定

## [2.3.61] - 2026-07-28

### Fixed

- thinking 容错（开启思考模式时）：
  - 标准 ``<entml:thinking>…</entml:thinking>`` 不变
  - ``<entml:thinking>…</thinking>`` 后接工具调用时，以 ``</thinking>`` 闭合思考块
  - 仅出现 plain ``<thinking>`` 开标签时同样进入思考块；``</entml:thinking>`` 与 ``</thinking>`` 均可闭合

## [2.3.60] - 2026-07-28

### Changed

- ``split_last_user_message``：移除回声启发式；仅末条 role 为 ``user`` 时构建 ``<current_user_message>``，否则全部归入 ``<entml:conversation_history>``

## [2.3.58] - 2026-07-28

### Fixed

- entml 工具 parameters JSON：``description`` 字段改为可读文本（内嵌引号不再输出 ``\\"``，换行为物理换行）；``pattern`` 等非 description 字段保持 JSON 转义

## [2.3.57] - 2026-07-28

### Fixed

- entml prompt：仅当消息列表**最后一条**为 ``user`` 时才构建 ``<current_user_message>``；末条为 assistant/tool 等时，全部内容归入 ``<entml:conversation_history>``，避免用户消息被误提为 current 且其后 assistant 轮次顺序错乱

## [2.3.56] - 2026-07-28

### Fixed

- entml 工具 Description：字面量 ``\\n`` 转为真实换行；``\\_`` / ``\\*`` 还原；改为 ``Description:\\n{正文}`` 纯文本排版，不再包 JSON 字符串引号

## [2.3.55] - 2026-07-28

### Fixed

- 流式 ``consume_stream_delta``：pending 改为 FIFO 队列，同一 ``feed`` 可产出多段 delta（并行多 invoke 不再只保留最后一段）
- 同一 chunk 内多个 ``</entml:invoke>`` 同时闭合时跳过 poll，由 ``_ensure_ready_invoke_stream_tails`` 按 invoke 顺序入队，避免 JSON 块顺序颠倒或漏发第一个 tool

## [2.3.54] - 2026-07-28

### Fixed

- 流式 partial_json：array/object 参数按 schema 原样嵌入 JSON（``todos`` 等为数组而非字符串），修复 TodoList 等 ``/todos must be array`` 校验失败
- 流式中断时 ``complete_stream_delta_if_needed`` 用 ``force_close`` 补齐合法 JSON 尾缀
- thinking 仅在出现 ``<entml:thinking>`` 开标签时解析；移除无开标签 orphan 闭标签重分类

## [2.3.53] - 2026-07-28

### Fixed

- 可见正文与 thinking 内 prose 提及 ``<entml:invoke>`` 不再被 hold/剥离；仅带真实 ``name=`` 的 invoke 开标签参与工具 holdback
- thinking 内逐字流式 invoke：开标签未闭合 ``>`` 前持续 hold，避免 `` name="Bash"`` 等被误吐进 thinking
- 恢复 thinking 内 ``<entml:parameter>`` 歧义 hold，与 invoke 开标签 hold 配合
- 漏写 ``<entml:thinking>`` 开标签仅有 ``</entml:thinking>`` 时：闭标签前正文重分类为 thinking，不再整段当作可见回答

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
