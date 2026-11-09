from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional


class CanonicalConfigService:
    """Static service for canonical configuration building, hashing, and validation."""

    @staticmethod
    def extract_asset_configuration(
            config_or_candidate: dict[str, Any],
            target_ticker: str,
    ) -> dict[str, Any]:
        if isinstance(config_or_candidate.get("assets"), list):
            for asset in config_or_candidate["assets"]:
                if isinstance(asset, dict):
                    sym = (
                        asset.get("ticker_symbol")
                        or f"{asset.get('base_ticker_symbol', '')}_{asset.get('quote_ticker_symbol', '')}".strip("_")
                    )
                    if sym == target_ticker:
                        return asset
            return {}
        return config_or_candidate

    @staticmethod
    def build_effective_config(  # pylint: disable=too-many-locals
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
        asset_cfg = CanonicalConfigService.extract_asset_configuration(candidate, ticker)

        raw_strategies = asset_cfg.get("strategies") or candidate.get("strategies") or []
        if not raw_strategies and (asset_cfg.get("strategy_weights") or candidate.get("strategy_weights")):
            weights = asset_cfg.get("strategy_weights") or candidate.get("strategy_weights")
            raw_strategies = [
                {"name": name, "weight": float(weight), "type": "EXPRESSION"}
                for name, weight in weights.items()
            ]

        canonical_strategies = []
        for s in raw_strategies:
            if isinstance(s, dict):
                entry: dict[str, Any] = {
                    "name": str(s.get("name", "")),
                    "weight": float(s.get("weight", 1.0)),
                    "type": str(s.get("type", "EXPRESSION")),
                }
                if "expression" in s:
                    entry["expression"] = str(s["expression"])
                if "enabled" in s:
                    entry["enabled"] = bool(s["enabled"])
                canonical_strategies.append(entry)
        sorted_strategies = sorted(canonical_strategies, key=lambda s: s.get("name", ""))

        raw_consensus = (
            asset_cfg.get("consensus")
            or candidate.get("consensus")
            or exp_spec.get("consensus")
            or {"buy": 1.0, "sell": 1.0}
        )
        if isinstance(raw_consensus, dict):
            consensus = {
                "buy": float(raw_consensus.get("buy", 1.0)),
                "sell": float(raw_consensus.get("sell", 1.0)),
            }
        else:
            consensus = {"buy": 1.0, "sell": 1.0}

        scheduling = {
            "timeframe": (
                asset_cfg.get("candles_timeframe")
                or (market_data_spec or {}).get("timeframe")
                or exp_spec.get("candles_timeframe", "MIN1")
            ),
        }

        exec_spec = execution_spec or candidate.get("execution_spec") or exp_spec.get("execution_spec") or {}
        execution = {
            "initial_balance": float(exec_spec.get("initial_balance", 10000.0)),
            "fee_rate": float(exec_spec.get("fee_rate", 0.001)),
            "slippage_ticks": int(exec_spec.get("slippage_ticks", 1)),
        }

        raw_protection = (
            asset_cfg.get("guard_config")
            or asset_cfg.get("protection")
            or candidate.get("protection")
            or exp_spec.get("protection")
            or {
                "max_drawdown_limit_pct": 15.0,
                "circuit_breaker": True,
            }
        )
        if isinstance(raw_protection, dict):
            protection = {
                "circuit_breaker": bool(raw_protection.get("circuit_breaker", True)),
                "max_drawdown_limit_pct": float(raw_protection.get("max_drawdown_limit_pct", 15.0)),
            }
        else:
            protection = {
                "circuit_breaker": True,
                "max_drawdown_limit_pct": 15.0,
            }

        return {
            "asset": {
                "ticker_symbol": ticker,
            },
            "consensus": consensus,
            "execution": execution,
            "protection": protection,
            "scheduling": scheduling,
            "strategies": sorted_strategies,
        }

    @staticmethod
    def compute_hash(effective_config: dict[str, Any]) -> str:
        canonical_json = json.dumps(
            effective_config,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @staticmethod
    def validate_commit_hash(commit_hash: Optional[str]) -> bool:
        if not commit_hash or commit_hash.strip().upper() == "HEAD":
            return False
        clean = commit_hash.strip()
        return bool(re.match(r"^[0-9a-fA-F]{7,64}$", clean))
