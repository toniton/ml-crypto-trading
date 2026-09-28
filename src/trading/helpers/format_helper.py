from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


class FormatHelper:
    @staticmethod
    def format_decimal(val: Any) -> str:
        if val is None:
            return "None"
        if not isinstance(val, Decimal):
            try:
                val = Decimal(str(val))
            except Exception:
                return str(val)
        if val == Decimal("inf"):
            return "Infinity"
        if val == Decimal("-inf"):
            return "-Infinity"
        s = f"{val:f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
            if s == "":
                s = "0"
        return s

    @staticmethod
    def parse_iso_datetime(ts: str) -> datetime:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)
