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


def test_entml_tool_descs_include_schema_types_and_required() -> None:
    out = format_entml_tool_descs([ASK_USER_TOOL])
    assert "**ask_user_input_v0**" in out
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
    assert "USE THIS TOOL WHENEVER YOU HAVE A QUESTION FOR THE USER.\n\n" in out
    assert "USE THIS TOOL WHEN:\n" in out
    assert "- User asks a question with 2-10 reasonable answers" in out
    assert "\\nUSE THIS TOOL WHEN" not in out


def test_entml_tool_descs_schema_key_order() -> None:
    out = format_entml_tool_descs([ASK_USER_TOOL])
    desc_pos = out.index('"description":')
    type_pos = out.index('"type": "object"', desc_pos)
    props_pos = out.index('"properties":', type_pos)
    required_pos = out.index('"required":', props_pos)
    assert desc_pos < type_pos < props_pos < required_pos
