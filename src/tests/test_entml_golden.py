"""Golden regression: entml parse + streaming snapshot locked to corpus digest."""

from __future__ import annotations

import os

import pytest
from fixtures.entml_golden import (
    build_case_record,
    build_golden_corpus,
    load_golden_corpus,
    write_golden_corpus,
)
from fixtures.simulated_llm_tool_responses import iter_cases_with_tools


def test_entml_golden_digest_matches() -> None:
    """Whole-corpus SHA256 must match committed golden (detect silent drift)."""
    expected = load_golden_corpus()
    actual = build_golden_corpus()
    assert actual["digest"] == expected["digest"], (
        "entml golden digest mismatch — run: "
        "python -m fixtures.entml_golden_update"
    )


@pytest.mark.parametrize("case", iter_cases_with_tools(), ids=lambda c: c.id)
def test_entml_case_matches_golden(case) -> None:
    """Per-case parse output and stream snapshots match golden records."""
    golden = load_golden_corpus()["cases"][case.id]
    actual = build_case_record(case)
    assert actual["names"] == golden["names"], case.id
    assert actual["args"] == golden["args"], case.id
    assert actual["clean"] == golden["clean"], case.id
    assert actual["snapshots"] == golden["snapshots"], case.id


if __name__ == "__main__":
    if os.environ.get("UPDATE_ENTML_GOLDEN") == "1":
        path = write_golden_corpus()
        print(f"Wrote {path}")
    else:
        pytest.main([__file__, "-q"])
