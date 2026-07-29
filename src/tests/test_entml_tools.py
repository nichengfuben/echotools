from echotools.exec.fncall.protocols.entml_schema import format_entml_tool_descs

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
    assert "Description:\nUSE THIS TOOL WHENEVER YOU HAVE A QUESTION FOR THE USER." in out
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
    assert (
        "Description:\nUSE THIS TOOL WHENEVER YOU HAVE A QUESTION FOR THE USER.\n\n"
        "USE THIS TOOL WHEN:\n"
    ) in out
    assert "\\n" not in out.split("```json")[0]
    assert "1-3 questions to ask the user" in out


def test_entml_tool_descs_schema_description_no_json_escapes() -> None:
    tool = {
        "type": "function",
        "function": {
            "name": "AskUserQuestion",
            "description": "Ask user",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            'Example: "Which library should we use for date formatting?" '
                            'If multiSelect is true, e.g. "Which features do you want?"'
                        ),
                    },
                    "header": {
                        "type": "string",
                        "description": 'Examples: "Auth method", "Library", "Approach".',
                    },
                    "source": {
                        "type": "string",
                        "description": '(e.g., "remember" for /remember command)',
                    },
                },
                "required": ["question"],
            },
        },
    }
    out = format_entml_tool_descs([tool])
    json_part = out.split("```json", 1)[1].split("```", 1)[0]
    assert '\\"' not in json_part
    assert 'Example: "Which library should we use for date formatting?"' in json_part
    assert 'Examples: "Auth method", "Library", "Approach".' in json_part
    assert '(e.g., "remember" for /remember command)' in json_part


def test_entml_tool_descs_pattern_field_keeps_regex_escapes() -> None:
    tool = {
        "type": "function",
        "function": {
            "name": "Validate",
            "description": "Validate input",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "pattern": "^[^\\n\\r]{1,200}$",
                    }
                },
            },
        },
    }
    out = format_entml_tool_descs([tool])
    json_part = out.split("```json", 1)[1].split("```", 1)[0]
    assert '"pattern": "^[^\\\\n\\\\r]{1,200}$"' in json_part


def test_entml_tool_descs_unescape_api_markdown_escapes() -> None:
    desc = (
        r"Launch agent.\n\n"
        r'Use `subagent\_type: "fork"` for forks.\n'
        r"**Don't peek.**"
    )
    tool = {
        "type": "function",
        "function": {
            "name": "Agent",
            "description": desc,
            "parameters": {"type": "object", "properties": {}},
        },
    }
    out = format_entml_tool_descs([tool])
    head = out.split("```json")[0]
    assert "subagent_type:" in head
    assert "fork" in head
    assert "\\_" not in head
    assert "**Don't peek.**" in head
    assert "\\n\\n" not in head
    assert "Launch agent.\n\n" in out


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
    assert out.startswith("### bash_tool\n\nDescription:\nRun a bash command")
    assert '"title": "BashInput"' in out
    assert '"name":' not in out
