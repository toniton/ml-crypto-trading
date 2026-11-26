from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Any, Optional

from api.interfaces.backtest_request import BacktestDataSourceType
from api.interfaces.experiment import CandidateType, TestSelection
from api.interfaces.trade_action import TradeAction
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.monitoring.activity_state import AssetActivityState
from src.backtest.analysis.drift_detector import DriftReport
from src.configuration.strategy_config import StrategyConfig
from src.events.agent_events import TradingActivityAnomalyDetectedEvent
from src.trading.strategies.strategy_registry import StrategyRegistry

DEFAULT_LOOKBACK_SECONDS = 86400.0
MIN_CONSENSUS_THRESHOLD = 0.5
CONSENSUS_RELAXATION_FACTOR = 0.8
MAX_ADDITIONAL_STRATEGIES = 3
ALT_MIX_NEW_WEIGHT = 1.2
ALT_MIX_EXISTING_WEIGHT = 0.7


@dataclass(frozen=True)
class SuggestedExperimentProposal:
    """Structured experiment suggestion generated for a NO_SIGNALS anomaly."""

    title: str
    description: str
    experiment_config: dict[str, Any]
    observed_window: dict[str, str]
    expected_effect: str
    risks: list[str] = field(default_factory=list)
    diagnostic_summary: dict[str, Any] = field(default_factory=dict)

    def to_proposed_change(self, diagnostic_markdown: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": "experiment_run",
            "experiment_config": self.experiment_config,
            "observed_window": self.observed_window,
            "expected_effect": self.expected_effect,
            "risks": list(self.risks),
            "diagnostic_summary": self.diagnostic_summary,
        }
        if diagnostic_markdown:
            payload["diagnostic_markdown"] = diagnostic_markdown
        return payload


class NoSignalsExperimentSuggester:
    """Builds candidate experiment configurations for NO_SIGNALS anomalies."""

    def __init__(
            self,
            configuration_service: ConfigurationService,
            strategy_registry: Optional[StrategyRegistry] = None,
            default_lookback_seconds: float = DEFAULT_LOOKBACK_SECONDS,
    ) -> None:
        self._configuration_service = configuration_service
        self._strategy_registry = strategy_registry
        self._default_lookback_seconds = default_lookback_seconds

    def suggest(
            self,
            event: TradingActivityAnomalyDetectedEvent,
            state: Optional[AssetActivityState] = None,
            drift: Optional[DriftReport] = None,
    ) -> SuggestedExperimentProposal:
        asset_config, base_commit = (
            self._configuration_service.get_asset_config_snapshot(event.asset)
        )
        observed_window = self._derive_observed_window(event, state, drift)
        candidates = self._build_candidates(asset_config, drift)
        experiment_name = self._build_experiment_name(event.asset, drift)

        experiment_config: dict[str, Any] = {
            "name": experiment_name,
            "ticker_symbol": event.asset,
            "base_commit_hash": base_commit or "",
            "test_selection": TestSelection.BACKTEST_ONLY.value,
            "data_source": {
                "source_type": BacktestDataSourceType.MARKET_DATA.value,
            },
            "period": {
                "start_time": observed_window["start_time"],
                "end_time": observed_window["end_time"],
            },
            "candidates": candidates,
        }

        diagnostic_summary: dict[str, Any] = {
            "anomaly_kind": event.anomaly_kind,
            "threshold_seconds": event.threshold,
            "drifted": drift.drifted if drift is not None else False,
            "fill_count_drift": drift.fill_count_drift if drift is not None else 0,
            "quantity_drift": str(drift.quantity_drift) if drift is not None else "0",
        }

        drift_note = (
            f" Backtest replay detected drift (fill count drift={drift.fill_count_drift}, "
            f"quantity drift={drift.quantity_drift})."
            if drift is not None and drift.drifted
            else ""
        )
        description = (
            f"{event.asset} is evaluating market data but producing no consensus signals "
            f"within {event.threshold:.0f}s.{drift_note} Run an isolated experiment across "
            f"{len(candidates)} candidate configuration(s) over the observed window to "
            f"compare strategy additions, weight tuning, and threshold sensitivity."
        )
        expected_effect = (
            f"Evaluates {len(candidates)} candidate strategy and weight configuration(s) "
            f"for {event.asset} over the observed market-data window on an isolated "
            f"experiment branch without modifying live trading configuration."
        )
        risks = [
            "Experiment runs on an isolated branch and does not alter live trading config.",
            "Observed-window backtest results may overfit a short market regime; "
            "validate with walk-forward testing before promoting any candidate.",
        ]
        return SuggestedExperimentProposal(
            title=f"Run strategy experiment — {event.asset}",
            description=description,
            experiment_config=experiment_config,
            observed_window=observed_window,
            expected_effect=expected_effect,
            risks=risks,
            diagnostic_summary=diagnostic_summary,
        )

    def _derive_observed_window(
            self,
            event: TradingActivityAnomalyDetectedEvent,
            state: Optional[AssetActivityState],
            drift: Optional[DriftReport],
    ) -> dict[str, str]:
        if drift is not None and drift.window_start and drift.window_end:
            return {
                "start_time": drift.window_start,
                "end_time": drift.window_end,
                "source": "backtest_drift_replay",
            }

        end_ts = self._parse_timestamp(event.detected_at) or time.time()
        earliest_activity = min(
            (
                ts
                for ts in (
                    state.last_market_data_at if state is not None else None,
                    state.last_evaluation_at if state is not None else None,
                )
                if ts is not None
            ),
            default=end_ts,
        )
        lookback = max(self._default_lookback_seconds, event.threshold * 4.0)
        start_ts = min(earliest_activity, end_ts) - lookback
        return {
            "start_time": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
            "end_time": datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat(),
            "source": "recent_market_data_window",
        }

    def _build_candidates(
            self,
            asset_config: Optional[dict[str, Any]],
            drift: Optional[DriftReport],
    ) -> list[dict[str, Any]]:
        strategies = (
            asset_config.get("strategies", []) if isinstance(asset_config, dict) else []
        )
        enabled_weights = self._extract_strategy_weights(strategies, enabled_only=True)
        disabled_names = [
            str(s["name"])
            for s in strategies
            if isinstance(s, dict) and s.get("name") and not s.get("enabled", True)
        ]
        existing_names = {
            str(s["name"])
            for s in strategies
            if isinstance(s, dict) and s.get("name")
        }

        candidates: list[dict[str, Any]] = [
            {
                "candidate_id": "cand_current",
                "name": "Current Configuration (Baseline)",
                "candidate_type": CandidateType.CURRENT_CONFIG.value,
                "strategy_weights": dict(enabled_weights),
                "description": "Current live strategy mix and weights over the observed window.",
            }
        ]

        if len(enabled_weights) >= 2 and len(set(enabled_weights.values())) > 1:
            candidates.append(
                {
                    "candidate_id": "cand_equal_weight",
                    "name": "Equal-Weight Strategies",
                    "candidate_type": CandidateType.EQUAL_WEIGHT.value,
                    "strategy_weights": {name: 1.0 for name in enabled_weights},
                    "description": "Equal weight (1.0) across all currently enabled strategies.",
                }
            )

        if disabled_names:
            reenabled_weights = dict(enabled_weights)
            for name in disabled_names:
                reenabled_weights[name] = 1.0
            candidates.append(
                {
                    "candidate_id": "cand_reenable_strategies",
                    "name": "Re-enable Disabled Strategies",
                    "candidate_type": CandidateType.CUSTOM_COMBINATION.value,
                    "strategy_weights": reenabled_weights,
                    "strategy_enabled_overrides": {name: True for name in disabled_names},
                    "description": (
                        f"Re-enables {', '.join(disabled_names)} alongside active strategies "
                        f"to widen consensus coverage."
                    ),
                }
            )

        tuned_candidate = self._build_tuned_sensitivity_candidate(
            asset_config, enabled_weights, drift
        )
        if tuned_candidate is not None:
            candidates.append(tuned_candidate)

        additional = self._select_additional_strategies(strategies, existing_names)
        if additional:
            candidates.extend(
                self._build_additional_strategy_candidates(additional, enabled_weights)
            )

        return candidates

    @classmethod
    def _build_additional_strategy_candidates(
            cls,
            additional: list[StrategyConfig],
            enabled_weights: dict[str, float],
    ) -> list[dict[str, Any]]:
        added_payloads = [cls._serialize_strategy(s) for s in additional]
        added_names = [str(s.name) for s in additional if s.name]
        combined_weights = dict(enabled_weights)
        for name in added_names:
            combined_weights[name] = 1.0
        result: list[dict[str, Any]] = [
            {
                "candidate_id": "cand_additional_strategies",
                "name": "Add Complementary Strategies",
                "candidate_type": CandidateType.CUSTOM_COMBINATION.value,
                "strategy_weights": combined_weights,
                "strategies_to_add": added_payloads,
                "description": (
                    f"Adds {', '.join(added_names)} at weight 1.0 to increase signal "
                    f"diversity in the observed market window."
                ),
            }
        ]
        if enabled_weights:
            alt_weights = {
                name: round(max(0.2, weight * ALT_MIX_EXISTING_WEIGHT), 2)
                for name, weight in enabled_weights.items()
            }
            for name in added_names:
                alt_weights[name] = ALT_MIX_NEW_WEIGHT
            result.append(
                {
                    "candidate_id": "cand_alternative_mix",
                    "name": "Alternative Strategy Mix & Weights",
                    "candidate_type": CandidateType.CUSTOM_COMBINATION.value,
                    "strategy_weights": alt_weights,
                    "strategies_to_add": added_payloads,
                    "description": (
                        f"Emphasizes {', '.join(added_names)} (weight {ALT_MIX_NEW_WEIGHT}) "
                        f"while down-weighting existing strategies for the observed window."
                    ),
                }
            )
        return result

    def _build_tuned_sensitivity_candidate(
            self,
            asset_config: Optional[dict[str, Any]],
            enabled_weights: dict[str, float],
            drift: Optional[DriftReport],
    ) -> Optional[dict[str, Any]]:
        consensus_override = self._suggest_consensus_override(asset_config)
        tuned_weights = self._suggest_rebalanced_weights(enabled_weights)
        weights_changed = tuned_weights != enabled_weights
        if not consensus_override and not weights_changed:
            return None

        parts: list[str] = []
        if weights_changed:
            parts.append("rebalanced strategy weights")
        if consensus_override:
            thresh_desc = ", ".join(
                f"{side}={val}" for side, val in sorted(consensus_override.items())
            )
            parts.append(f"relaxed consensus thresholds ({thresh_desc})")
        if drift is not None and drift.drifted:
            parts.append("aligned with drift replay window")

        candidate: dict[str, Any] = {
            "candidate_id": "cand_tuned_weights_thresholds",
            "name": "Tuned Weights & Threshold Sensitivity",
            "candidate_type": CandidateType.CUSTOM_COMBINATION.value,
            "strategy_weights": tuned_weights,
            "description": (
                f"Tests {' and '.join(parts)} to check if stricter thresholds caused "
                f"signal starvation."
            ),
        }
        if consensus_override:
            candidate["consensus_override"] = consensus_override
        return candidate

    def _select_additional_strategies(
            self,
            current_strategies: list[Any],
            existing_names: set[str],
    ) -> list[StrategyConfig]:
        if self._strategy_registry is None:
            return []

        available: list[StrategyConfig] = []
        for name in self._strategy_registry.keys():
            if name in existing_names:
                continue
            strategy = self._strategy_registry.find(name)
            if strategy is not None and strategy.name:
                available.append(strategy)
        if not available:
            return []

        active_actions = {
            str(s.get("action", "")).upper()
            for s in current_strategies
            if isinstance(s, dict) and s.get("enabled", True) and s.get("action")
        }
        missing_buy = TradeAction.BUY.value not in active_actions
        missing_sell = TradeAction.SELL.value not in active_actions

        selected: list[StrategyConfig] = []
        if missing_buy:
            buy_cand = next(
                (s for s in available if s.action == TradeAction.BUY), None
            )
            if buy_cand is not None:
                selected.append(buy_cand)
        if missing_sell:
            sell_cand = next(
                (s for s in available if s.action == TradeAction.SELL), None
            )
            if sell_cand is not None and sell_cand not in selected:
                selected.append(sell_cand)

        for strategy in available:
            if len(selected) >= MAX_ADDITIONAL_STRATEGIES:
                break
            if strategy not in selected:
                selected.append(strategy)

        return selected[:MAX_ADDITIONAL_STRATEGIES]

    @staticmethod
    def _extract_strategy_weights(
            strategies: list[Any],
            enabled_only: bool = True,
    ) -> dict[str, float]:
        weights: dict[str, float] = {}
        for strat in strategies:
            if not isinstance(strat, dict):
                continue
            name = strat.get("name")
            if not name:
                continue
            if enabled_only and not strat.get("enabled", True):
                continue
            weights[str(name)] = float(strat.get("weight", 1.0))
        return weights

    @staticmethod
    def _suggest_consensus_override(
            asset_config: Optional[dict[str, Any]],
    ) -> Optional[dict[str, float]]:
        if not isinstance(asset_config, dict):
            return None
        consensus = asset_config.get("consensus")
        if not isinstance(consensus, dict):
            return None

        override: dict[str, float] = {}
        for side in ("buy", "sell"):
            raw = consensus.get(side)
            if isinstance(raw, (int, float)) and raw > MIN_CONSENSUS_THRESHOLD:
                relaxed = round(
                    max(MIN_CONSENSUS_THRESHOLD, float(raw) * CONSENSUS_RELAXATION_FACTOR),
                    2,
                )
                if relaxed < float(raw):
                    override[side] = relaxed
        return override or None

    @staticmethod
    def _suggest_rebalanced_weights(
            enabled_weights: dict[str, float],
    ) -> dict[str, float]:
        if not enabled_weights:
            return {}
        tuned: dict[str, float] = {}
        for name, weight in enabled_weights.items():
            if weight < 1.0:
                tuned[name] = round(min(1.0, weight + 0.25), 2)
            elif weight > 1.5:
                tuned[name] = round(max(1.0, weight * 0.85), 2)
            else:
                tuned[name] = weight
        return tuned

    @staticmethod
    def _serialize_strategy(strategy: StrategyConfig) -> dict[str, Any]:
        data = strategy.model_dump(mode="json", exclude_none=True)
        data["enabled"] = True
        data.setdefault("weight", 1.0)
        return data

    @staticmethod
    def _parse_timestamp(raw: Optional[str]) -> Optional[float]:
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return None

    @staticmethod
    def _build_experiment_name(
            asset: str,
            drift: Optional[DriftReport],
    ) -> str:
        suffix = "no-signals-drift" if drift is not None and drift.drifted else "no-signals"
        return f"Anomaly {asset} ({suffix})"
