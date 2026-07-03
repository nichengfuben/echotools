"""Terminal output sanitization -- strip ephemeral CSI/OSC sequences.

This module provides functions to clean terminal output for history
storage, preserving display-affecting sequences while removing
ephemeral ones that would pollute saved history.
"""

from __future__ import annotations

import re
from typing import Tuple

# CSI sequences to strip (ephemeral, not display-affecting)
# Device Status Report: ESC [ c, ESC [ 0 c, ESC [ ? 6 c
# Cursor Position Response: ESC [ ... R  (where ... is numeric params)
# Device Attributes: ESC [ > 0 c, ESC [ > 1 c, ESC [ > 2 c
_STRIP_CSI_PATTERNS = [
    re.compile(r"\x1b\[[0-9;]*[cR]"),       # Device status, cursor position response
    re.compile(r"\x1b\[\?[0-9;]*[a-zA-Z]"), # Private mode queries
]

# OSC sequences to strip (ephemeral color queries)
# Terminal color queries: ESC ] 10 ; ... BEL, ESC ] 11 ; ... BEL, etc.
_STRIP_OSC_PATTERNS = [
    re.compile(r"\x1b\]1[012];[^\x07\x1b]*(?:\x07|\x1b\\)"),  # Color queries
    re.compile(r"\x1b\]1[012];rgb:[0-9a-f/]+\x07"),            # Color responses
]


def sanitize_terminal_history_chunk(
    chunk: str, pending: str = ""
) -> Tuple[str, str]:
    """Strip ephemeral CSI/OSC sequences from terminal output.

    This function removes sequences that are ephemeral (device status
    reports, cursor position responses, color queries) while preserving
    display-affecting sequences (colors, cursor movement, scrolling).

    Args:
        chunk: Raw terminal output chunk.
        pending: Incomplete control sequence from previous chunk.

    Returns:
        Tuple of (cleaned_text, new_pending) where cleaned_text is
        the sanitized output and new_pending is any incomplete sequence
        that should be prepended to the next chunk.
    """
    # Prepend any pending incomplete sequence from previous chunk
    text = pending + chunk
    new_pending = ""

    # Check for incomplete escape sequence at the end
    # (escape sequence that doesn't terminate within this chunk)
    if text.endswith("\x1b"):
        # ESC at end might be start of new sequence
        text = text[:-1]
        new_pending = "\x1b"
    elif "\x1b" in text:
        # Check if last ESC is the start of an incomplete sequence
        last_esc_pos = text.rfind("\x1b")
        suffix = text[last_esc_pos:]
        # If suffix doesn't contain a valid terminator, it's incomplete
        if not re.match(r"\x1b\[[0-9;]*[A-Z]", suffix) and \
           not re.match(r"\x1b\][0-9;]*[\x07\x1b\\]", suffix) and \
           not re.match(r"\x1b[\[\]()#][0-9;]*[A-Z]", suffix):
            # Might be incomplete, keep it as pending
            text = text[:last_esc_pos]
            new_pending = suffix

    # Strip ephemeral CSI sequences
    for pattern in _STRIP_CSI_PATTERNS:
        text = pattern.sub("", text)

    # Strip ephemeral OSC sequences
    for pattern in _STRIP_OSC_PATTERNS:
        text = pattern.sub("", text)

    return text, new_pending
