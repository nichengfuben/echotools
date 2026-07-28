from echotools.exec.fncall.protocols.entml_think.parse import (
    EntmlThinkingStreamFilter,
    has_unclosed_entml_thinking,
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


def test_has_unclosed_entml_thinking_streaming_prefix() -> None:
    assert has_unclosed_entml_thinking("<entml:think")
    assert not has_unclosed_entml_thinking("<entml:thinking>done</entml:thinking>")


def test_entml_thinking_stream_filter() -> None:
    filt = EntmlThinkingStreamFilter()
    parts = []
    for chunk in ["hello ", "<entml:thinking>rea", "son</entml:thinking> world"]:
        parts.extend(filt.feed(chunk))
    parts.extend(filt.finalize())
    kinds = {kind for kind, _ in parts}
    assert "thinking" in kinds
    assert "content" in kinds
    thinking = "".join(t for k, t in parts if k == "thinking")
    content = "".join(t for k, t in parts if k == "content")
    assert thinking == "reason"
    assert "hello" in content
    assert "world" in content


def test_entml_thinking_stream_incremental() -> None:
    """块内正文应随 feed 增量输出，而不是等闭合标签。"""
    filt = EntmlThinkingStreamFilter()
    events = []
    for chunk in [
        "<entml:thinking>\n",
        "The user has initiated",
        " a conversation",
        ".\n",
        "</entml:thinking>",
        "\n\nHello!",
    ]:
        out = filt.feed(chunk)
        events.append((chunk, out))

    # 开标签后的正文分片应立即产生 thinking，而非空列表
    mid_thinking = [
        text
        for chunk, outs in events
        if chunk not in ("</entml:thinking>", "\n\nHello!")
        for kind, text in outs
        if kind == "thinking"
    ]
    assert mid_thinking, "thinking body must stream before close tag"
    assert any("initiated" in t for t in mid_thinking)

    # 闭合后应立刻放出正文
    close_events = next(outs for chunk, outs in events if chunk == "</entml:thinking>")
    assert close_events == [] or all(k == "thinking" for k, _ in close_events)
    tail = next(outs for chunk, outs in events if chunk == "\n\nHello!")
    assert any(k == "content" and "Hello" in t for k, t in tail)

    # 累积结果与 batch 语义一致（首片去前导空白）
    all_parts = [p for _, outs in events for p in outs]
    all_parts.extend(filt.finalize())
    thinking = "".join(t for k, t in all_parts if k == "thinking")
    content = "".join(t for k, t in all_parts if k == "content")
    assert thinking.startswith("The user has initiated")
    assert "conversation" in thinking
    assert "Hello!" in content
    assert "<entml:thinking>" not in content


def test_entml_thinking_hold_close_prefix() -> None:
    filt = EntmlThinkingStreamFilter()
    parts = []
    parts.extend(filt.feed("<entml:thinking>ab"))
    parts.extend(filt.feed("</entml:think"))  # 真前缀，不应误当正文吐出
    assert "".join(t for k, t in parts if k == "thinking") == "ab"
    parts.extend(filt.feed("ing>cd"))
    thinking = "".join(t for k, t in parts if k == "thinking")
    content = "".join(t for k, t in parts if k == "content")
    assert thinking == "ab"
    assert content == "cd"


def test_plain_thinking_open_entml_close_batch() -> None:
    text = "<thinking>\nplan step\n</entml:thinking>\nanswer"
    content, thinking = split_entml_thinking(text)
    assert thinking == "plan step"
    assert "answer" in content
    assert "<thinking>" not in content


def test_plain_thinking_open_fault_close_batch() -> None:
    text = "<thinking>\nplan step\n</thinking>\nanswer"
    content, thinking = split_entml_thinking(text)
    assert thinking == "plan step"
    assert "answer" in content


def test_plain_thinking_stream_entml_close() -> None:
    filt = EntmlThinkingStreamFilter()
    parts = []
    for chunk in ["<thinking>\nplan", "\n</entml:thinking>\n", "hello"]:
        parts.extend(filt.feed(chunk))
    parts.extend(filt.finalize())
    thinking = "".join(t for k, t in parts if k == "thinking")
    content = "".join(t for k, t in parts if k == "content")
    assert thinking.strip() == "plan"
    assert "hello" in content


def test_plain_thinking_stream_fault_close() -> None:
    filt = EntmlThinkingStreamFilter()
    parts = []
    for chunk in ["<thinking>\nplan\n</thinking>\n", "hello"]:
        parts.extend(filt.feed(chunk))
    parts.extend(filt.finalize())
    thinking = "".join(t for k, t in parts if k == "thinking")
    content = "".join(t for k, t in parts if k == "content")
    assert thinking.strip() == "plan"
    assert "hello" in content
    assert not filt.in_open_thinking()
