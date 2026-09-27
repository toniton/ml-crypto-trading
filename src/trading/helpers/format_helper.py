from __future__ import annotations

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
