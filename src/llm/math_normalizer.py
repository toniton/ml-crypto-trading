from __future__ import annotations

import re
from typing import Pattern

_DISPLAY_OPEN: Pattern[str] = re.compile(r"\\\[ ?")
_DISPLAY_CLOSE: Pattern[str] = re.compile(r" ?\\\]")
_INLINE_OPEN: Pattern[str] = re.compile(r"\\\( ?")
_INLINE_CLOSE: Pattern[str] = re.compile(r" ?\\\)")
_EXCESS_NEWLINES: Pattern[str] = re.compile(r"\n{3,}")
_DOLLAR_RE: Pattern[str] = re.compile(r"(?<!\\)\$")


def _escape_dollars_in_math(text: str) -> str:
    """Escapes bare ``$`` inside ``$$ ... $$`` blocks so KaTeX renders currency
    amounts literally instead of raising a `misplaced $` error. Dollar signs in
    prose (even ``$$`` segments) are left untouched."""
    parts = text.split("$$")
    escaped = [
        _DOLLAR_RE.sub(r"\$", part) if index % 2 else part
        for index, part in enumerate(parts)
    ]
    return "$$".join(escaped)


def normalize_math_delimiters(text: str) -> str:
    """Rewrites LaTeX math into canonical ``$$ ... $$`` display blocks.

    Every math expression (display ``\\[ ... \\]`` and inline ``\\(...\\)``) is
    promoted to its own container surrounded by blank lines so the frontend can
    render it as a whitespace-separated block:

    ::

        $$ ... $$

    The LaTeX body is preserved verbatim for KaTeX/MathJax. Currency amounts
    such as ``$1,466.70`` in ordinary text are untouched.
    """
    output = text
    output = _DISPLAY_OPEN.sub("\n\n$$\n", output)
    output = _DISPLAY_CLOSE.sub("\n$$\n\n", output)
    output = _INLINE_OPEN.sub("\n\n$$\n", output)
    output = _INLINE_CLOSE.sub("\n$$\n\n", output)
    output = _escape_dollars_in_math(output)
    return _EXCESS_NEWLINES.sub("\n\n", output)


class DelimiterStream:
    """Applies :func:`normalize_math_delimiters` to a token stream chunk by chunk.

    A trailing lone backslash is buffered so a ``\\[`` / ``\\]`` or ``\\(`` /
    ``\\)`` pair split across token chunks still reassembles into a ``$$`` block.
    """

    def __init__(self, max_hold: int = 16):
        self._buffer = ""
        self._max_hold = max_hold

    def push(self, chunk: str) -> str:
        self._buffer += chunk
        emit_before = len(self._buffer) - self._hold_length()
        output = normalize_math_delimiters(self._buffer[:emit_before])
        self._buffer = self._buffer[emit_before:]
        return output

    def flush(self) -> str:
        output = normalize_math_delimiters(self._buffer)
        self._buffer = ""
        return output

    def _hold_length(self) -> int:
        if len(self._buffer) <= self._max_hold:
            tail = self._buffer
        else:
            tail = self._buffer[-self._max_hold:]
        if tail.endswith("\\") and not tail.endswith("\\\\"):
            return 1
        return 0
