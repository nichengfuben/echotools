"""Dev parity checker: batch parse vs streaming snapshot (uses golden helpers)."""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "src/tests")
from fixtures.entml_golden import _args, _invoke_snapshots, _names
from fixtures.simulated_llm_tool_responses import SIMULATED_LLM_RESPONSES, TOOLS, tools_for_case

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser

proto = get_protocol("entml")

mismatches: list[str] = []
for case in SIMULATED_LLM_RESPONSES:
    if not case.expect_names:
        continue
    tools = tools_for_case(case)
    _, batch_calls = proto.parse(case.response, tools)
    snapshots = _invoke_snapshots(case.response, batch_calls, tools)
    if len(snapshots) != len(batch_calls):
        mismatches.append(
            f"{case.id}: snapshot count {len(snapshots)} != batch {len(batch_calls)}"
        )
        continue
    for i, (batch_arg, snap) in enumerate(zip(_args(batch_calls), snapshots)):
        if batch_arg != snap:
            mismatches.append(
                f"{case.id}[{i}] batch={batch_arg!r} stream={snap!r}"
            )

for chunk in (1, 5, 17):
    for case in SIMULATED_LLM_RESPONSES:
        if not case.expect_names:
            continue
        tools = tools_for_case(case)
        parser = FncallStreamParser(protocol=proto, tools=tools)
        merged_list: list[str] = []
        cur = ""
        for j in range(0, len(case.response), chunk):
            ready = parser.feed(case.response[j : j + chunk])
            delta = parser.consume_stream_delta()
            if delta:
                cur += delta[1]
            if ready:
                merged_list.append(cur)
                cur = ""
        parser.finalize()
        if cur:
            merged_list.append(cur)
        _, batch_calls = proto.parse(case.response, tools)
        if len(merged_list) != len(batch_calls):
            mismatches.append(
                f"stream count {case.id} chunk={chunk}: "
                f"merged={len(merged_list)} batch={len(batch_calls)}"
            )
            continue
        for mi, (merged, call) in enumerate(zip(merged_list, batch_calls)):
            try:
                ma = json.loads(merged)
            except json.JSONDecodeError as exc:
                mismatches.append(
                    f"stream merged {case.id}[{mi}] chunk={chunk}: {exc} {merged[:60]!r}"
                )
                continue
            ba = json.loads(call["function"]["arguments"])
            if ma != ba:
                mismatches.append(
                    f"stream merged {case.id}[{mi}] chunk={chunk}: "
                    f"batch={ba!r} merged={ma!r}"
                )

print("\n".join(mismatches) if mismatches else "ALL OK")
