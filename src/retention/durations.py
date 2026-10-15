from __future__ import annotations

import re
from datetime import timedelta
from typing import Optional, Union


class RetentionDuration:
    KEEP_TOKEN = "KEEP"
    _DURATION_PATTERN = re.compile(r"^(?P<value>\d+)(?P<unit>[dhms])$", re.IGNORECASE)
    _UNIT_SECONDS = {"d": 86400, "h": 3600, "m": 60, "s": 1}

    @classmethod
    def parse(cls, raw: Optional[Union[str, int, timedelta]]) -> Optional[timedelta]:
        """Parse a retention duration such as ``90d``, ``12h``, ``30m``, ``45s`` or ``KEEP``.

        Returns ``None`` for ``KEEP`` (indefinite retention). Raises ``ValueError`` for
        unsupported syntax so misconfigured policies fail fast.
        """
        if raw is None:
            return None
        if isinstance(raw, timedelta):
            return raw
        if isinstance(raw, int):
            return timedelta(seconds=raw)

        text = str(raw).strip()
        if not text:
            raise ValueError("Empty retention duration")
        if text.upper() == cls.KEEP_TOKEN:
            return None

        match = cls._DURATION_PATTERN.match(text)
        if not match:
            raise ValueError(
                f"Invalid retention duration '{text}'. Use <number><d|h|m|s> or KEEP."
            )
        value = int(match.group("value"))
        unit = match.group("unit").lower()
        return timedelta(seconds=value * cls._UNIT_SECONDS[unit])

    @classmethod
    def format(cls, delta: Optional[timedelta]) -> str:
        if delta is None:
            return cls.KEEP_TOKEN
        total = int(delta.total_seconds())
        if total % 86400 == 0 and total != 0:
            return f"{total // 86400}d"
        if total % 3600 == 0 and total != 0:
            return f"{total // 3600}h"
        if total % 60 == 0 and total != 0:
            return f"{total // 60}m"
        return f"{total}s"


KEEP_TOKEN = RetentionDuration.KEEP_TOKEN
parse_duration = RetentionDuration.parse
format_duration = RetentionDuration.format
