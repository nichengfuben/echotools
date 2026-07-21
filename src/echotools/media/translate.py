"""Generic translation utilities for chat/completions-based translation platforms.

Provides helpers used by translation platform adapters (DeepL, Google Translate,
Azure Translator, Yandex Translate, etc.) to extract text from OpenAI-format
messages, split translated text for streaming, and format responses.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Tuple


def extract_text_from_messages(
    messages: List[Dict[str, Any]],
    default_source: str = "auto",
) -> Tuple[str, str, str]:
    """Extract translation text, source lang, and target lang from OpenAI-format messages.

    Convention used by all translation platforms:
    - ``system`` message content = source language hint
    - last ``user`` message content = text to translate

    Args:
        messages: OpenAI chat/completions message list.
        default_source: Fallback source language when no system message is present.

    Returns:
        ``(text, source_lang, target_lang)`` tuple.
        ``target_lang`` defaults to ``"en"`` (override at call-site).
    """
    text = ""
    source_lang = default_source
    target_lang = "en"

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system" and content:
            source_lang = content.strip()
        elif role == "user" and content:
            text = content

    return text, source_lang, target_lang


def _sentence_chunks(text: str) -> List[str]:
    parts = re.split(r'(?<=[.!?。！？\n])', text)
    short_chunks = [p for p in parts if p]
    return short_chunks if len(short_chunks) > 1 else [text]


def _accumulate_sentence_chunks(text: str, max_chunk: int) -> List[str]:
    chunks: List[str] = []
    current = ""
    sentences = text.replace("。", ".\n").replace("！", "!\n").replace("？", "?\n").split("\n")
    for sentence in sentences:
        if len(current) + len(sentence) > max_chunk and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current += sentence
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _word_fallback_chunks(text: str) -> List[str]:
    words = text.split()
    if len(words) <= 5:
        return [text]
    return [" ".join(words[i:i + 5]) for i in range(0, len(words), 5)]


def split_text_chunks(text: str, max_chunk: int = 5000) -> List[str]:
    """Split text into chunks at sentence boundaries for streaming simulation."""
    if not text:
        return []

    if len(text) <= max_chunk:
        return _sentence_chunks(text)

    chunks = _accumulate_sentence_chunks(text, max_chunk)
    if len(chunks) <= 1:
        chunks = _word_fallback_chunks(text)
    return chunks


def format_translation_response(
    translated_text: str,
    model: str = "translate",
) -> Dict[str, Any]:
    """Format a translation result as an OpenAI chat completion response.

    Args:
        translated_text: The translated text content.
        model: Model name to include in the response.

    Returns:
        OpenAI-compatible chat completion response dict.
    """
    return {
        "id": "translate-{}".format(int(time.time())),
        "object": "chat.completion",
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": translated_text},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
