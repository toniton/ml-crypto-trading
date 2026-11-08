from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional


def build_canonical_effective_config(
        candidate: dict[str, Any],
        experiment: dict[str, Any],
        execution_spec: Optional[dict[str, Any]] = None,
        market_data_spec: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    exp_spec = experiment.get("spec") or {}
    ticker = (
        (market_data_spec or {}).get("ticker_symbol")
        or candidate.get("ticker_symbol")
        or experiment.get("ticker_symbol")
        or exp_spec.get("ticker_symbol")
        or "BTC_USD"
    )

    strategies = candidate.get("strategies") or []
    if not strategies and candidate.get("strategy_weights"):
        strategies = [
            {"name": name, "weight": float(weight), "type": "EXPRESSION"}
            for name, weight in candidate["strategy_weights"].items()
        ]
    sorted_strategies = sorted(strategies, key=lambda s: s.get("name", ""))

    consensus = (
        candidate.get("consensus")
        or exp_spec.get("consensus")
        or {"buy": 1.0, "sell": 1.0}
    )

    scheduling = {
        "timeframe": (market_data_spec or {}).get("timeframe") or exp_spec.get("candles_timeframe", "MIN1"),
    }

    exec_spec = execution_spec or candidate.get("execution_spec") or exp_spec.get("execution_spec") or {}
    execution = {
        "initial_balance": float(exec_spec.get("initial_balance", 10000.0)),
        "fee_rate": float(exec_spec.get("fee_rate", 0.001)),
        "slippage_ticks": int(exec_spec.get("slippage_ticks", 1)),
    }

    protection = candidate.get("protection") or exp_spec.get("protection") or {
        "max_drawdown_limit_pct": 15.0,
        "circuit_breaker": True,
    }

    return {
        "asset": {
            "ticker_symbol": ticker,
        },
        "candidate_id": candidate.get("candidate_id", ""),
        "consensus": consensus,
        "execution": execution,
        "protection": protection,
        "scheduling": scheduling,
        "strategies": sorted_strategies,
    }


def compute_canonical_config_hash(effective_config: dict[str, Any]) -> str:
    canonical_json = json.dumps(
        effective_config,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def validate_commit_hash(commit_hash: Optional[str]) -> bool:
    if not commit_hash or commit_hash.strip().upper() == "HEAD":
        return False
    clean = commit_hash.strip()
    return bool(re.match(r"^[0-9a-fA-F]{7,64}$", clean))
