from echotools.exec.fncall.protocols.entml_thinking_parse import (
    EntmlThinkingStreamFilter,
    split_entml_thinking,
)


def test_split_entml_thinking() -> None:
    text = (
        "prefix\n<entml:thinking>\nstep one\n</entml:thinking>\n"
        "answer tail"
    )
    content, thinking = split_entml_thinking(text)
    assert thinking == "step one"
    assert "prefix" in content
    assert "answer tail" in content
    assert "<entml:thinking>" not in content


def test_entml_thinking_stream_filter() -> None:
    filt = EntmlThinkingStreamFilter()
    parts = []
    for chunk in ["hello ", "<entml:thinking>rea", "son</entml:thinking> world"]:
        parts.extend(filt.feed(chunk))
    parts.extend(filt.finalize())
    kinds = {kind for kind, _ in parts}
    assert "thinking" in kinds
    assert "content" in kinds
