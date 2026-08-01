"""Build and load golden records for entml parse + streaming snapshot regression."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.protocols.entml_patterns import (
    extract_attr_value,
    iter_actionable_entml_invoke_blocks,
    resolve_known_tool_names,
)
from echotools.exec.fncall.protocols.entml_stream import build_streaming_json_snapshot
from echotools.exec.fncall.shared.coercion import _build_param_schema_index
from fixtures.simulated_llm_tool_responses import (
    SimulatedCase,
    iter_cases_with_tools,
    tools_for_case,
)

_GOLDEN_PATH = Path(__file__).with_name("entml_golden.json")


def _names(calls: List[Dict[str, Any]]) -> List[str]:
    return [(c.get("function") or {}).get("name") or "" for c in calls]


def _args(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for call in calls:
        raw = (call.get("function") or {}).get("arguments") or "{}"
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            parsed = {"__raw__": raw}
        out.append(parsed)
    return out


def _invoke_snapshots(
    text: str,
    calls: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    schema_index = _build_param_schema_index(tools)
    known = resolve_known_tool_names(tools, schema_index)
    blocks = list(iter_actionable_entml_invoke_blocks(text, known_names=known))
    if len(blocks) != len(calls):
        return []
    snapshots: List[Dict[str, Any]] = []
    for (_start, _end, attrs, body), call in zip(blocks, calls):
        name = extract_attr_value(attrs, "name") or _names([call])[0]
        snap = build_streaming_json_snapshot(
            body + "</entml:invoke>",
            tool_name=name.replace("\\_", "_"),
            schema_index=schema_index,
        )
        if not snap:
            snapshots.append({})
            continue
        snapshots.append(json.loads(snap))
    return snapshots


def build_case_record(case: SimulatedCase) -> Dict[str, Any]:
    proto = get_protocol("entml")
    tools = tools_for_case(case)
    clean, calls = proto.parse(case.response, tools)
    return {
        "names": _names(calls),
        "args": _args(calls),
        "clean": clean.strip(),
        "snapshots": _invoke_snapshots(case.response, calls, tools),
    }


def build_golden_corpus() -> Dict[str, Any]:
    records: Dict[str, Any] = {}
    for case in iter_cases_with_tools():
        records[case.id] = build_case_record(case)
    digest_src = json.dumps(records, sort_keys=True, ensure_ascii=False)
    return {
        "version": 1,
        "digest": hashlib.sha256(digest_src.encode("utf-8")).hexdigest(),
        "cases": records,
    }


def load_golden_corpus() -> Dict[str, Any]:
    return json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))


def write_golden_corpus(path: Optional[Path] = None) -> Path:
    target = path or _GOLDEN_PATH
    corpus = build_golden_corpus()
    target.write_text(
        json.dumps(corpus, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target
