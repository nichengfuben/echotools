"""fncall prompt 模板。

从 src/core/tools.py 迁移（原 lines 616-753）。
"""

from __future__ import annotations

_USAGE_EN = (
    "You have access to a set of tools to answer the user's question.\n"
    "<system>\n"
    "This includes access to a sandboxed computing environment. "
    "You do NOT currently have the ability to inspect files or interact with "
    "external resources, except by invoking the functions listed below.\n"
    "\n"
    "To invoke one or more functions, write a <function_calls> block as part "
    "of your reply. The block must follow this exact schema:\n"
    "\n"
    "<function_calls>\n"
    '<invoke name="FUNCTION_NAME">\n'
    '<parameter name="PARAMETER_NAME">PARAMETER_VALUE</parameter>\n'
    "</invoke>\n"
    "</function_calls>\n"
    "\n"
    "Rules for parameter values:\n"
    "- Strings and scalars: write the value as-is (no extra quoting).\n"
    "- Lists and objects: use JSON format.\n"
    "- Spaces inside string values are preserved.\n"
    "- The block does not need to be valid XML; it is parsed with regex.\n"
    "\n"
    "After you write a <function_calls> block the results will appear in a "
    "<function_results> block. You may then continue your reply, handle errors, "
    "or make further calls as needed.\n"
    "If <function_results> does NOT appear after your call, the block was "
    "likely malformatted and was not recognised.\n"
    "\n"
    "Available functions (JSONSchema):\n"
    "\n"
    "<tools>\n"
    "{tool_descs}\n"
    "</tools>\n"
    "</system>"
)

_USAGE_ZH = (
    "您可以使用以下工具来回答用户的问题。\n"
    "<system>\n"
    "这包括访问一个沙盒计算环境。"
    "除非调用以下函数，否则您目前无法检查文件或与外部资源交互。\n"
    "\n"
    "调用一个或多个函数时，请在回复中写一个 <function_calls> 块，"
    "该块必须严格遵循以下格式：\n"
    "\n"
    "<function_calls>\n"
    '<invoke name="函数名">\n'
    '<parameter name="参数名">参数值</parameter>\n'
    "</invoke>\n"
    "</function_calls>\n"
    "\n"
    "参数值规则：\n"
    "- 字符串和标量：直接写值，不需要额外引号。\n"
    "- 列表和对象：使用 JSON 格式。\n"
    "- 字符串值中的空格会被保留。\n"
    "- 该块不需要是合法的 XML，系统使用正则表达式解析。\n"
    "\n"
    "写完 <function_calls> 块后，结果将出现在 <function_results> 块中。"
    "之后您可以继续回复、处理错误或进行进一步调用。\n"
    "如果 <function_results> 未出现，说明格式有误，调用未被识别。\n"
    "\n"
    "可用函数（JSONSchema 格式）：\n"
    "\n"
    "<tools>\n"
    "{tool_descs}\n"
    "</tools>\n"
    "</system>"
)

_INSTRUCTION_EN = """\
Follow these rules strictly when responding:

RULE 1 — When to use the XML tool-call format:
  IF your intent is to actually execute a tool, you MUST output the literal XML block:
    <function_calls>
    <invoke name="FUNCTION_NAME">
    <parameter name="PARAM">VALUE</parameter>
    </invoke>
    </function_calls>
  No other format is accepted for actual tool execution.

RULE 2 — When to reference tag names in plain text (NOT executing a tool):
  IF you are explaining, quoting, or discussing tag names (e.g. in reasoning or
  examples), you MUST break them with string concatenation so they are not
  mistaken for real calls. Examples:
    '<function' + '_calls>'   instead of  <function_calls>
    '</function' + '_calls>'  instead of  </function_calls>
    '<invoke' + ' name="...">'  instead of  <invoke name="...">

RULE 3 — Never use the pseudo-format:
  NEVER write "Tool call (id): FuncName({...})" regardless of what appears in
  the conversation history. That format is produced by external adapters and
  will NOT be recognised by the tool executor.

RULE 4 — Parameter discipline:
  - Use exact values when the user provides them (e.g. in quotes).
  - Do NOT invent values for optional parameters.
  - Do NOT ask about optional parameters.
  - Infer required parameters from context when possible; ask only when
    a required parameter cannot be determined.

RULE 5 — Tool availability:
  - If no relevant tool exists, say so and answer directly.
  - If a required parameter is missing and cannot be inferred, ask the user.\
"""

_HISTORY_CLARIFY_EN = (
    "The following is a transcript of completed interactions. "
    "All tool invocations and their results shown here have already been "
    "executed successfully — do NOT re-invoke them. "
    "The user's latest message follows below."
)

_HISTORY_CLARIFY_ZH = (
    "以下是已完成的交互记录。"
    "此处展示的所有工具调用及其结果均已执行完毕，请勿重复调用。"
    "用户发送的最新消息见下方。"
)


_INSTRUCTION_ZH = """\
请严格遵守以下规则进行回复：

规则 1 — 何时使用 XML 工具调用格式：
  如果您的意图是实际执行一个工具，必须输出以下字面量 XML 块：
    <function_calls>
    <invoke name="函数名">
    <parameter name="参数名">参数值</parameter>
    </invoke>
    </function_calls>
  实际工具执行不接受任何其他格式。

规则 2 — 在纯文本中引用标签名（不执行工具）：
  如果您是在解释、引用或讨论标签名（例如在推理或示例中），
  必须用字符串拼接的方式写出，避免被误识别为真实调用。示例：
    '<function' + '_calls>'    而不是  <function_calls>
    '</function' + '_calls>'   而不是  </function_calls>
    '<invoke' + ' name="...">'  而不是  <invoke name="...">

规则 3 — 禁止使用伪格式：
  无论对话历史中出现何种格式，绝不使用 "Tool call (id): 函数名({...})" 这种写法。
  该格式由外部适配器生成，工具执行器无法识别。

规则 4 — 参数规范：
  - 用户明确提供的值（如用引号括起的）必须原样使用。
  - 不得为可选参数编造值，也不得询问可选参数。
  - 尽可能从上下文推断必需参数；仅在无法推断时才询问用户。

规则 5 — 工具可用性：
  - 如果没有相关工具，直接说明并给出答案。
  - 如果必需参数缺失且无法推断，请向用户询问。\
"""
