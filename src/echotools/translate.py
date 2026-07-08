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


def split_text_chunks(text: str, max_chunk: int = 5000) -> List[str]:
    """Split text into chunks at sentence boundaries for streaming simulation.

    Splits on common sentence-ending punctuation (``.!?`` and CJK equivalents).
    Falls back to word-group chunking when no sentence breaks are found.

    Args:
        text: Complete translated text.
        max_chunk: Maximum characters per chunk.

    Returns:
        List of text fragments.
    """
    if not text:
        return []

    if len(text) <= max_chunk:
        # Even short text benefits from sentence splitting for streaming
        parts = re.split(r'(?<=[.!?。！？\n])', text)
        short_chunks = [p for p in parts if p]
        if len(short_chunks) <= 1:
            return [text]
        return short_chunks

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

    # Fallback: if no sentence breaks found, split by words
    if len(chunks) <= 1:
        words = text.split()
        if len(words) > 5:
            chunk_size = 5
            chunks = [
                " ".join(words[i:i + chunk_size])
                for i in range(0, len(words), chunk_size)
            ]
        else:
            chunks = [text]

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
