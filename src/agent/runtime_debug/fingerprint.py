from __future__ import annotations

import hashlib
import re

from src.agent.runtime_debug.models import RuntimeErrorEvent


def normalize_error_message(message: str) -> str:
    if not message:
        return ""
    normalized = message.strip().lower()
    # Replace UUIDs with placeholder
    normalized = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "<uuid>",
        normalized,
    )
    # Replace hex hashes
    normalized = re.sub(r"\b[0-9a-f]{40,64}\b", "<hash>", normalized)
    # Replace ISO timestamps
    normalized = re.sub(
        r"\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}:\d{2}(\.\d+)?(z|[+-]\d{2}:\d{2})?",
        "<timestamp>",
        normalized,
    )
    # Replace floating point numbers with generic number placeholder to avoid varying amounts breaking fingerprint
    normalized = re.sub(r"\b\d+\.\d+\b", "<float>", normalized)
    return normalized.strip()


def compute_error_fingerprint(event: RuntimeErrorEvent) -> str:
    provider = (event.exchange or "").upper().strip()
    operation = (event.operation or "").lower().strip()
    exchange_code = str(event.exchange_code or "").strip()
    component = (event.component or "").lower().strip()
    normalized_message = normalize_error_message(event.message)

    raw_key = f"{provider}:{operation}:{exchange_code}:{normalized_message}:{component}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
