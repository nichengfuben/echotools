"""schema_validate：coerce 之后的 JSON Schema 边界校验。"""

from __future__ import annotations

import pytest

from echotools.exec.fncall.protocols.entml_schema.validate import (
    ToolArgValidationError,
    validate_param_value,
    validate_tool_arguments,
)
from echotools.exec.fncall.protocols.entml_tool.values import coerce_entml_arguments
from echotools.exec.fncall.shared.coercion import (
    _build_param_schema_index,
    is_null_literal,
    schema_allows_null,
)


def test_schema_allows_null_union():
    assert schema_allows_null({"type": ["string", "null"]})
    assert not schema_allows_null({"type": "string"})


def test_is_null_literal():
    assert is_null_literal("")
    assert is_null_literal("null")
    assert not is_null_literal("hello")


def test_validate_enum_rejects_unknown():
    issues = validate_param_value(
        "bad",
        {"type": "string", "enum": ["a", "b"]},
        path="mode",
    )
    assert len(issues) == 1
    assert "mode" in issues[0].path


def test_validate_type_mismatch_after_coerce_shape():
    issues = validate_param_value("not-int", {"type": "integer"}, path="n")
    assert issues


def test_coerce_entml_arguments_strict_enum():
    tools = [
        {
            "function": {
                "name": "pick",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "color": {"type": "string", "enum": ["red", "blue"]},
                    },
                },
            }
        }
    ]
    idx = _build_param_schema_index(tools)
    with pytest.raises(ToolArgValidationError) as exc:
        coerce_entml_arguments(
            {"color": "green"},
            "pick",
            idx,
            strict=True,
        )
    assert "green" in str(exc.value) or exc.value.to_llm_feedback()


def test_coerce_entml_arguments_soft_skips_validate():
    tools = [
        {
            "function": {
                "name": "pick",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "color": {"type": "string", "enum": ["red", "blue"]},
                    },
                },
            }
        }
    ]
    idx = _build_param_schema_index(tools)
    out = coerce_entml_arguments({"color": "green"}, "pick", idx, strict=False)
    assert out["color"] == "green"


def test_validate_required_missing():
    idx = {"fn": {"x": {"type": "string"}}}
    issues = validate_tool_arguments({}, "fn", idx, required=["x"])
    assert any("missing" in i.message for i in issues)


def test_null_union_coerce_via_param_value():
    from echotools.exec.fncall.protocols.entml_tool.values import (
        coerce_entml_parameter_value,
    )

    val = coerce_entml_parameter_value(
        "null",
        {"type": ["string", "null"]},
    )
    assert val is None
