from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


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

    @staticmethod
    def to_json_compatible(val: Any) -> Any:
        if val is None or isinstance(val, (str, int, float, bool)):
            result = val
        elif isinstance(val, Decimal):
            result = int(val) if val % 1 == 0 else float(val)
        elif isinstance(val, (datetime, date)):
            result = val.isoformat()
        elif isinstance(val, Enum):
            result = val.value
        elif isinstance(val, UUID):
            result = str(val)
        elif isinstance(val, dict):
            result = {str(k): FormatHelper.to_json_compatible(v) for k, v in val.items()}
        elif isinstance(val, (list, tuple, set)):
            result = [FormatHelper.to_json_compatible(x) for x in val]
        elif hasattr(val, "to_dict") and callable(val.to_dict):
            result = FormatHelper.to_json_compatible(val.to_dict())
        else:
            result = str(val)
        return result
