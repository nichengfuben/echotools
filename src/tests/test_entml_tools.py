from echotools.exec.fncall.protocols.entml_tools import format_entml_tool_descs

ASK_USER_TOOL = {
    "type": "function",
    "function": {
        "name": "ask_user_input_v0",
        "description": (
            "USE THIS TOOL WHENEVER YOU HAVE A QUESTION FOR THE USER.\n\n"
            "USE THIS TOOL WHEN:\n"
            "- User asks a question with 2-10 reasonable answers"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "items": {
                        "properties": {
                            "options": {
                                "items": {"type": "string"},
                                "maxItems": 4,
                                "minItems": 2,
                                "type": "array",
                            },
                            "question": {"type": "string"},
                            "type": {
                                "default": "single_select",
                                "enum": [
                                    "single_select",
                                    "multi_select",
                                    "rank_priorities",
                                ],
                                "type": "string",
                            },
                        },
                        "required": ["question", "options"],
                        "type": "object",
                    },
                    "maxItems": 3,
                    "minItems": 1,
                    "type": "array",
                    "description": "1-3 questions to ask the user",
                }
            },
            "required": ["questions"],
        },
    },
}


def test_entml_tool_descs_heading_and_description_outside_json() -> None:
    out = format_entml_tool_descs([ASK_USER_TOOL])
    assert "### ask_user_input_v0" in out
    assert "**ask_user_input_v0**" not in out
    assert 'Description: "USE THIS TOOL WHENEVER YOU HAVE A QUESTION FOR THE USER.' in out
    # name / top-level description 不再塞进 parameters JSON
    assert '"name": "ask_user_input_v0"' not in out
    assert out.count("```json") == 1


def test_entml_tool_descs_include_schema_types_and_required() -> None:
    out = format_entml_tool_descs([ASK_USER_TOOL])
    assert '"type": "object"' in out
    assert '"type": "array"' in out
    assert '"type": "string"' in out
    assert '"enum":' in out
    assert '"required":' in out
    assert '"minItems":' in out
    assert '"maxItems":' in out
    assert '"default": "single_select"' in out


def test_entml_tool_descs_expand_multiline_description() -> None:
    out = format_entml_tool_descs([ASK_USER_TOOL])
    # 外置 Description 为 JSON 字符串字面量，换行以 \n 转义
    assert "USE THIS TOOL WHENEVER YOU HAVE A QUESTION FOR THE USER.\\n\\nUSE THIS TOOL WHEN:\\n" in out
    # parameters 内嵌 description 仍可展开多行
    assert "1-3 questions to ask the user" in out


def test_entml_tool_descs_schema_key_order() -> None:
    out = format_entml_tool_descs([ASK_USER_TOOL])
    # parameters 块内：properties 先于 type
    json_start = out.index("```json")
    props_pos = out.index('"properties":', json_start)
    type_pos = out.index('"type": "object"', json_start)
    required_pos = out.index('"required":', json_start)
    assert props_pos < required_pos
    assert props_pos < type_pos


def test_entml_tool_descs_matches_design_shape() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "bash_tool",
                "description": "Run a bash command in the container",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "title": "Bash command to run in container",
                            "type": "string",
                        },
                        "description": {
                            "title": "Why I'm running this command",
                            "type": "string",
                        },
                    },
                    "required": ["command", "description"],
                    "title": "BashInput",
                },
            },
        }
    ]
    out = format_entml_tool_descs(tools)
    assert out.startswith("### bash_tool\n\nDescription: \"Run a bash command")
    assert '"title": "BashInput"' in out
    assert '"name":' not in out
