"""Temporary parity checker — delete after fix."""
import json
import re
import sys

sys.path.insert(0, "src/tests")
from fixtures.simulated_llm_tool_responses import SIMULATED_LLM_RESPONSES, TOOLS

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_stream_json import (
    build_streaming_json_snapshot,
)

proto = get_protocol("entml")
from echotools.exec.fncall.shared.coercion import _build_param_schema_index

schema_index = _build_param_schema_index(TOOLS)
pat = re.compile(r'<entml:invoke name="([^"]+)">(.*?)</entml:invoke>', re.S)

mismatches = []
for case in SIMULATED_LLM_RESPONSES:
    if not case.expect_names:
        continue
    _, batch_calls = proto.parse(case.response, TOOLS)
    for i, m in enumerate(pat.finditer(case.response)):
        name, body = m.group(1), m.group(2)
        snap = build_streaming_json_snapshot(
            body + "</entml:invoke>",
            tool_name=name.replace("\\_", "_"),
            schema_index=schema_index,
        )
        try:
            stream_args = json.loads(snap)
        except json.JSONDecodeError as e:
            mismatches.append(f"{case.id}[{i}] JSON error: {e} snap={snap[:80]!r}")
            continue
        batch_args = json.loads(batch_calls[i]["function"]["arguments"])
        if stream_args != batch_args:
            mismatches.append(f"{case.id}[{i}] batch={batch_args!r} stream={stream_args!r}")

# stream merged test
for chunk in (1, 5, 17):
    for case in SIMULATED_LLM_RESPONSES:
        if not case.expect_names:
            continue
        parser = FncallStreamParser(protocol=proto, tools=TOOLS)
        merged_list = []
        cur = ""
        for j in range(0, len(case.response), chunk):
            ready = parser.feed(case.response[j : j + chunk])
            d = parser.consume_stream_delta()
            if d:
                cur += d[1]
            if ready:
                merged_list.append(cur)
                cur = ""
        parser.finalize()
        if cur:
            merged_list.append(cur)
        _, batch_calls = proto.parse(case.response, TOOLS)
        if len(merged_list) != len(batch_calls):
            mismatches.append(
                f"stream count {case.id} chunk={chunk}: merged={len(merged_list)} batch={len(batch_calls)}"
            )
            continue
        for mi, (merged, call) in enumerate(zip(merged_list, batch_calls)):
            try:
                ma = json.loads(merged)
            except json.JSONDecodeError as e:
                mismatches.append(f"stream merged {case.id}[{mi}] chunk={chunk}: {e} {merged[:60]!r}")
                continue
            ba = json.loads(call["function"]["arguments"])
            if ma != ba:
                mismatches.append(f"stream merged {case.id}[{mi}] chunk={chunk}: batch={ba!r} merged={ma!r}")

print("\n".join(mismatches) if mismatches else "ALL OK")
