from __future__ import annotations

"""模型输出分支矩阵：batch / stream / partial_json / 参数类型 必须与 schema 规则一致。"""

import json
import re
from typing import Any, Dict, List, Optional

import pytest
from fixtures.simulated_llm_tool_responses import (
    REQUIRED_MODEL_BRANCHES,
    SimulatedCase,
    covered_model_branches,
    iter_cases_with_tools,
    tools_for_case,
)

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_stream import build_streaming_json_snapshot
from echotools.exec.fncall.shared.coercion import _build_param_schema_index

_INVOKE_RE = re.compile(
    r"<entml:invoke\b([^>]*)>([\s\S]*?)</entml:invoke>",
    re.IGNORECASE,
)

CHUNK_SIZES = [1, 3, 5, 7, 17, 64]


def _batch_calls(text: str, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    _, calls = get_protocol("entml").parse(text, tools)
    return calls


def _merged_stream_jsons(
    text: str,
    tools: List[Dict[str, Any]],
    chunk_size: int,
) -> List[str]:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=tools)
    merged_list: List[str] = []
    current = ""
    current_name: Optional[str] = None
    step = max(1, chunk_size)
    for i in range(0, len(text), step):
        merged_at_start = len(merged_list)
        ready = parser.feed(text[i : i + step])
        while True:
            delta = parser.consume_stream_delta()
            if not delta:
                break
            name, piece = delta
            if current_name is not None and name != current_name:
                merged_list.append(current)
                current = ""
            current_name = name
            current += piece
        if ready:
            if current:
                merged_list.append(current)
                current = ""
                current_name = None
            streamed = len(merged_list) - merged_at_start
            for call in ready[streamed:]:
                merged_list.append(call["function"]["arguments"])
    comp = parser.complete_stream_delta_if_needed()
    if comp:
        current += comp[1]
    parser.finalize()
    if current:
        merged_list.append(current)
    return merged_list


def _invoke_tool_name(attrs: str) -> str:
    from echotools.exec.fncall.protocols.entml_patterns import (
        extract_attr_value,
        normalize_entml_name,
    )

    name = extract_attr_value(attrs, "name") or ""
    return normalize_entml_name(name.replace("\\_", "_"))


def _assert_args_match_expect_types(
    parsed: Dict[str, Any],
    expect: Dict[str, Any],
    *,
    case_id: str,
    tool_name: str,
) -> None:
    for key, expected in expect.items():
        actual = parsed[key]
        assert type(actual) is type(expected), (
            f"{case_id}.{tool_name}.{key}: got {type(actual).__name__} want "
            f"{type(expected).__name__} ({actual!r} vs {expected!r})"
        )


def test_model_branch_corpus_covers_required_branches() -> None:
    covered = covered_model_branches()
    missing = REQUIRED_MODEL_BRANCHES - covered
    assert not missing, f"missing branches: {sorted(missing)}"


@pytest.mark.parametrize("case", iter_cases_with_tools(), ids=lambda c: f"{c.branch}/{c.id}")
def test_branch_batch_parse(case: SimulatedCase) -> None:
    tools = tools_for_case(case)
    calls = _batch_calls(case.response, tools)
    names = [c["function"]["name"] for c in calls]
    args = [json.loads(c["function"]["arguments"]) for c in calls]
    assert names == case.expect_names, case.id
    assert args == case.expect_args, case.id


@pytest.mark.parametrize("case", iter_cases_with_tools(), ids=lambda c: f"{c.branch}/{c.id}")
def test_branch_batch_arg_types(case: SimulatedCase) -> None:
    tools = tools_for_case(case)
    calls = _batch_calls(case.response, tools)
    for call, expect in zip(calls, case.expect_args):
        parsed = json.loads(call["function"]["arguments"])
        assert parsed == expect
        _assert_args_match_expect_types(
            parsed,
            expect,
            case_id=case.id,
            tool_name=call["function"]["name"],
        )


@pytest.mark.parametrize("case", iter_cases_with_tools(), ids=lambda c: f"{c.branch}/{c.id}")
@pytest.mark.parametrize("chunk_size", CHUNK_SIZES, ids=lambda n: f"chunk{n}")
def test_branch_stream_merged_matches_batch(case: SimulatedCase, chunk_size: int) -> None:
    tools = tools_for_case(case)
    calls = _batch_calls(case.response, tools)
    merged_list = _merged_stream_jsons(case.response, tools, chunk_size)
    assert len(merged_list) == len(calls), (
        f"{case.id} chunk={chunk_size}: merged={len(merged_list)} batch={len(calls)}"
    )
    for merged, call in zip(merged_list, calls):
        batch_args = json.loads(call["function"]["arguments"])
        merged_args = json.loads(merged)
        assert merged_args == batch_args
        for key, value in batch_args.items():
            assert type(merged_args[key]) is type(value), (
                f"{case.id}.{key}: stream type {type(merged_args[key])} != batch {type(value)}"
            )


@pytest.mark.parametrize("case", iter_cases_with_tools(), ids=lambda c: f"{c.branch}/{c.id}")
def test_branch_closed_snapshot_equals_batch(case: SimulatedCase) -> None:
    tools = tools_for_case(case)
    calls = _batch_calls(case.response, tools)
    schema = _build_param_schema_index(tools)
    for i, match in enumerate(_INVOKE_RE.finditer(case.response)):
        name = _invoke_tool_name(match.group(1))
        body = match.group(2) + "</entml:invoke>"
        snap = build_streaming_json_snapshot(body, tool_name=name, schema_index=schema)
        batch_args = json.loads(calls[i]["function"]["arguments"])
        merged_args = json.loads(snap)
        assert merged_args == batch_args
        for key, value in batch_args.items():
            assert type(merged_args[key]) is type(value), case.id


@pytest.mark.parametrize("case", iter_cases_with_tools(), ids=lambda c: f"{c.branch}/{c.id}")
def test_branch_stream_monotonic_char_by_char(case: SimulatedCase) -> None:
    tools = tools_for_case(case)
    calls = _batch_calls(case.response, tools)
    finals = [c["function"]["arguments"] for c in calls]
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=tools)
    invoke_idx = 0
    merged = ""
    for ch in case.response:
        ready = parser.feed(ch)
        delta = parser.consume_stream_delta()
        if delta:
            merged += delta[1]
            assert finals[invoke_idx].startswith(merged), (
                f"{case.id} invoke={invoke_idx} drift: {merged!r}"
            )
        if ready:
            assert merged == finals[invoke_idx], case.id
            invoke_idx += 1
            merged = ""
    assert invoke_idx == len(finals)


def test_type_hint_priority_in_parse_and_stream() -> None:
    """模型 type=str 优先于 schema integer；stream 与 batch 类型一致。"""
    case = next(
        c for c in iter_cases_with_tools() if c.id == "model_type_str_overrides_schema_int"
    )
    tools = tools_for_case(case)
    calls = _batch_calls(case.response, tools)
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["days"] == "3"
    assert type(args["days"]) is str

    merged = _merged_stream_jsons(case.response, tools, chunk_size=5)[0]
    stream_args = json.loads(merged)
    assert stream_args["days"] == "3"
    assert type(stream_args["days"]) is str
