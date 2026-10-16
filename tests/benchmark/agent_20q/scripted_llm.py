from __future__ import annotations
# pylint: disable=too-many-return-statements,line-too-long

from typing import Any, AsyncIterator, List, Optional, Type

from api.interfaces.backtest_request import BacktestDataSourceType
from src.agent.backtest.models import BacktestAgentRequest, BacktestTimeRange
from src.agent.configuration.models import ConfigChange, ConfigurationProposal
from src.agent.decision_investigation.models import DecisionExplanation
from src.agent.performance_analysis.models import MetricQueryIntent
from src.agent.portfolio_insights.models import PortfolioAnalysisResult, PortfolioQueryIntent
from src.agent.router.models import (
    AgentGoal,
    AgentIntent,
    AgentReferences,
    AgentRoute,
    ConfigurationAction,
)
from src.core.interfaces.llm_adapter import ChatTurn, LlmAdapter
from tests.benchmark.agent_20q.models import QuestionSpec
from tests.benchmark.agent_20q.scenarios import TWENTY_QUESTIONS, SeededBenchmarkEnvironment


class RecordingToolProxy:
    def __init__(self, key_name: str, tool: Any, recorder: list[str]) -> None:
        self._key_name = key_name
        self._tool = tool
        self._recorder = recorder
        self.name = getattr(tool, "name", key_name)

    def _record(self) -> None:
        if self._key_name not in self._recorder:
            self._recorder.append(self._key_name)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        self._record()
        return self._tool.invoke(*args, **kwargs)

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        self._record()
        return self._tool._run(*args, **kwargs)  # pylint: disable=protected-access

    def __getattr__(self, item: str) -> Any:
        if item == "backtest_service":
            self._record()
        return getattr(self._tool, item)


class BenchmarkScriptedLlmAdapter(LlmAdapter):
    def __init__(self, env: SeededBenchmarkEnvironment) -> None:
        self._env = env
        self.invoked_tools: list[str] = []
        self.routed_intent: Optional[str] = None
        self._active_question: Optional[QuestionSpec] = None
        self._tools: dict[str, RecordingToolProxy] = {}
        self._bind_env_tools(env.tools)

    def _bind_env_tools(self, tool_map: dict[str, Any]) -> None:
        for key, tool in tool_map.items():
            proxy = RecordingToolProxy(key, tool, self.invoked_tools)
            self._tools[key.lower()] = proxy
            tool_name = getattr(tool, "name", key).lower()
            self._tools[tool_name] = proxy
            if key == "backtest":
                self._tools["run_backtest"] = proxy

    def reset_turn_tracking(self) -> None:
        self.invoked_tools.clear()
        self.routed_intent = None
        self._active_question = None

    def bind_tools(self, tools: List[Any]) -> None:
        for tool in tools:
            name = getattr(tool, "name", str(tool)).lower()
            self._tools[name] = RecordingToolProxy(name, tool, self.invoked_tools)

    def get_tool(self, name: str) -> Optional[Any]:
        return self._tools.get(name.lower())

    def invoke_tool(self, name: str, payload: Optional[dict[str, Any]] = None) -> str:
        proxy = self.get_tool(name)
        if proxy is None:
            return f"Tool '{name}' not bound."
        return str(proxy.invoke(payload or {}))

    @staticmethod
    def match_question(prompt: str) -> QuestionSpec:
        normalized = prompt.strip().lower()
        for spec in TWENTY_QUESTIONS:
            for candidate in spec.all_prompts:
                if candidate.strip().lower() in normalized or normalized in candidate.strip().lower():
                    return spec

        keyword_map: list[tuple[list[str], str]] = [
            (["tick-1901", "schedule tick through order execution", "contrast it with no-order"], "Q19"),
            (["btc_usd placed an order", "btc_usd has not submitted", "stage of the btc_usd schedule tick"], "Q03"),
            (["healthy", "health state", "actively trading right now"], "Q01"),
            (["balances", "available cash", "open orders"], "Q02"),
            (["failing", "rejected", "longer to execute", "timeouts"], "Q04"),
            (["buy or sell", "ord-501", "dec-501"], "Q05"),
            (["bollingerstrategy", "strategy's signal rejected", "dec-601"], "Q06"),
            (["between the current configuration", "ord-legacy-missing", "commit ref is missing"], "Q07"),
            (["recommend", "propose", "configuration change"], "Q08"),
            (["24 hours", "7 days", "30 days", "24h, 7d, and 30d"], "Q09"),
            (["contributed most", "reconcile", "double-counted"], "Q10"),
            (["market regime", "trending_up vs ranging"], "Q11"),
            (["diverging from its backtest", "drifted from its backtest", "simulated fills vs live fills"], "Q12"),
            (["profitable on historical", "historical backtest", "2026-09-01"], "Q13"),
            (["walk-forward", "candidate configuration"], "Q14"),
            (["exp_901", "what triggered it", "experiment run"], "Q15"),
            (["justify a new experiment", "inactive or drifted", "research experiment for cro_usd"], "Q16"),
            (["concentration risk", "portfolio exposure", "missing price data"], "Q17"),
            (["risk manager or guard", "dec-1801", "prevent a trade"], "Q18"),
            (["expire", "retained", "ret_run_01", "deleted or skipped"], "Q20"),
        ]
        for keywords, qid in keyword_map:
            if any(k in normalized for k in keywords):
                return next(s for s in TWENTY_QUESTIONS if s.question_id == qid)
        return TWENTY_QUESTIONS[0]

    def _ensure_question(self, prompt: str) -> QuestionSpec:
        if self._active_question is None:
            self._active_question = self.match_question(prompt)
        return self._active_question

    def generate(
        self,
        prompt: str,
        history: Optional[List[ChatTurn]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        spec = self._ensure_question(prompt)
        return self._synthesize_text_for_question(spec)

    async def stream(
        self,
        prompt: str,
        history: Optional[List[ChatTurn]] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        yield self.generate(prompt, history=history, system_prompt=system_prompt)

    def generate_structured(self, schema: Type[Any], prompt: str, system_prompt: str) -> Any:
        spec = self._ensure_question(prompt)

        if schema is AgentRoute:
            route = self._build_route(spec)
            self.routed_intent = str(getattr(route.intent, "value", route.intent))
            return route

        if schema is PortfolioQueryIntent:
            return PortfolioQueryIntent(
                quote_currency="USD",
                exchange="CRYPTO_DOT_COM",
                focus_areas=["balances", "open_orders", "drawdown", "concentration"],
            )

        if schema is PortfolioAnalysisResult:
            return self._build_portfolio_analysis(spec)

        if schema is MetricQueryIntent:
            return self._build_metric_query_intent(spec)

        if schema is BacktestAgentRequest:
            return BacktestAgentRequest(
                ticker_symbol="BTC_USD",
                time_range=BacktestTimeRange(mode="relative", duration_seconds=7200),
                data_source=BacktestDataSourceType.MARKET_DATA,
                fee_rate=0.001,
                slippage_ticks=2,
                latency_ms=100.0,
            )

        if schema is ConfigurationProposal:
            return self._build_configuration_proposal()

        if schema is DecisionExplanation:
            return self._build_decision_explanation(spec)

        return schema.model_construct()

    def _build_route(self, spec: QuestionSpec) -> AgentRoute:
        intent = spec.expected_intents[0]
        if intent in {AgentIntent.SYSTEM_HELP, AgentIntent.RISK_ANALYSIS}:
            for candidate_intent in spec.expected_intents:
                if candidate_intent in {
                    AgentIntent.RUNTIME_DEBUG,
                    AgentIntent.PORTFOLIO_REVIEW,
                    AgentIntent.DECISION_INVESTIGATION,
                    AgentIntent.PERFORMANCE_ANALYSIS,
                    AgentIntent.CONFIGURATION,
                    AgentIntent.BACKTEST,
                }:
                    intent = candidate_intent
                    break
        if spec.question_id in ("Q12", "Q14"):
            intent = AgentIntent.PERFORMANCE_ANALYSIS

        if spec.question_id == "Q08":
            return AgentRoute(
                intent=AgentIntent.CONFIGURATION,
                action=ConfigurationAction.MODIFY,
                goal=AgentGoal(
                    objective="Propose validated configuration change for ETH_USD",
                    target_asset="ETH_USD",
                ),
            )
        if spec.question_id in {"Q05", "Q07"}:
            return AgentRoute(
                intent=AgentIntent.DECISION_INVESTIGATION,
                references=AgentReferences(
                    asset="BTC_USD",
                    commit_hash=self._env.commit_v1,
                ),
            )
        if spec.question_id in {"Q06", "Q15", "Q18"}:
            return AgentRoute(
                intent=intent,
                references=AgentReferences(
                    asset="BTC_USD",
                    commit_hash=self._env.commit_v2,
                ),
            )
        if spec.question_id == "Q13":
            return AgentRoute(
                intent=AgentIntent.BACKTEST,
                goal=AgentGoal(objective="Run historical backtest on BTC_USD", target_asset="BTC_USD"),
            )
        return AgentRoute(
            intent=intent,
            goal=AgentGoal(objective=spec.canonical_prompt),
        )

    def _build_portfolio_analysis(self, spec: QuestionSpec) -> PortfolioAnalysisResult:
        if spec.question_id == "Q02":
            exchange_balances = self.invoke_tool(
                "exchange_read_api",
                {"operation": "get_balances", "exchange": "CRYPTO_DOT_COM"},
            )
            open_btc = self.invoke_tool("get_open_orders", {"ticker_symbol": "BTC_USD"})
            open_eth = self.invoke_tool("get_open_orders", {"ticker_symbol": "ETH_USD"})
            portfolio_summary = self.invoke_tool("portfolio_summary", {"quote_currency": "USD"})
            return PortfolioAnalysisResult(
                overall_health="HEALTHY",
                findings=[
                    "Authoritative Exchange Balance vs. Locally Calculated Portfolio Exposure & Reserved Cash:",
                    exchange_balances,
                    open_btc,
                    open_eth,
                    portfolio_summary,
                ],
                recommendations=[
                    "Clearly distinguish authoritative exchange balance ($4400 USD total on CRYPTO_DOT_COM, "
                    "0.125 BTC) from locally reserved cash ($1500 reserved across open orders ord-101 and ord-102, "
                    "leaving $2900 locally available cash)."
                ],
            )

        portfolio_summary = self.invoke_tool("portfolio_summary", {"quote_currency": "USD"})
        exchange_balances = self.invoke_tool(
            "exchange_read_api",
            {"operation": "get_balances", "exchange": "CRYPTO_DOT_COM"},
        )
        return PortfolioAnalysisResult(
            overall_health="WARNING",
            findings=[
                portfolio_summary,
                exchange_balances,
            ],
            recommendations=[
                "BTC_USD concentration is 64.52% (exceeding 50% limit), current drawdown is 4.2% (within 10% limit), "
                "reserved orders include ord-101 and ord-102, and SOL_USD has Unavailable Price Data ([PRICE UNAVAILABLE])."
            ],
        )

    @staticmethod
    def _build_metric_query_intent(spec: QuestionSpec) -> MetricQueryIntent:
        if spec.question_id == "Q11":
            return MetricQueryIntent(
                metric_names=["trading.realized_pnl_usd"],
                lookback_seconds=604800,
                analysis_focus="strategy performance by regime",
            )
        return MetricQueryIntent(
            metric_names=["trading.realized_pnl_usd"],
            lookback_seconds=604800,
            analysis_focus="strategy attribution and performance",
        )

    def _build_configuration_proposal(self) -> ConfigurationProposal:
        _ = self.invoke_tool("get_configuration", {"ticker_symbol": "ETH_USD"})
        return ConfigurationProposal(
            summary=(
                f"Hypothesis (not proof of better performance): adjust ETH_USD min_quantity from 0.0001 to 0.001 "
                f"on base commit {self._env.commit_v2[:8]}. Requires operator approval before applying."
            ),
            changes=[
                ConfigChange(
                    path="assets.ETH_USD.min_quantity",
                    old_value=0.0001,
                    new_value=0.001,
                    reason=(
                        "ETH_USD min_quantity adjustment from 0.0001 to 0.001 is a hypothesis (not proof of better "
                        "performance) to prevent exchange MIN_NOTIONAL rejections; requires human approval."
                    ),
                )
            ],
            risks=["Slightly larger minimum order notional on ETH_USD."],
            expected_effect="Eliminate sub-notional order rejections on ETH_USD.",
        )

    def _build_decision_explanation(self, spec: QuestionSpec) -> DecisionExplanation:
        if spec.question_id == "Q05":
            decision_output = self.invoke_tool(
                "inspect_trading_decision",
                {"action": "get_by_id", "decision_id": "dec-501"},
            )
            return DecisionExplanation(
                summary=(
                    "Based strictly on recorded evidence for decision dec-501: Rio executed BTC_USD BUY order ord-501 "
                    "after consensus quorum (RSIStrategy + MACDStrategy) and sizing formula "
                    "`0.05 * available_cash / close_price` = 0.025."
                ),
                causal_story=decision_output,
                key_factors=["dec-501", "ord-501", "RSIStrategy", "MACDStrategy", "0.025"],
            )

        if spec.question_id == "Q06":
            decision_output = self.invoke_tool(
                "inspect_trading_decision",
                {"action": "get_by_id", "decision_id": "dec-601"},
            )
            return DecisionExplanation(
                summary=(
                    "Persisted rejection reason on decision dec-601: BollingerStrategy BUY vote (weight 0.25) "
                    "was rejected due to QUORUM_NOT_MET (25.0% < 60.0% quorum threshold)."
                ),
                causal_story=decision_output,
                key_factors=["dec-601", "BollingerStrategy", "QUORUM_NOT_MET", "60.0%"],
            )

        if spec.question_id == "Q07":
            diff_output = self.invoke_tool(
                "get_configuration_history",
                {
                    "action": "diff",
                    "commit_hash": self._env.commit_v1,
                    "target_hash": self._env.commit_v2,
                },
            )
            _ = self.invoke_tool("get_configuration", {"ticker_symbol": "BTC_USD"})
            _ = self.invoke_tool(
                "inspect_trading_decision",
                {"action": "get_by_id", "decision_id": "dec-501"},
            )
            return DecisionExplanation(
                summary=(
                    f"Configuration diff between order ord-501 commit ({self._env.commit_v1[:8]}) and current HEAD "
                    f"({self._env.commit_v2[:8]}): BTC_USD min_quantity changed from 0.001 to 0.005."
                ),
                causal_story=(
                    f"{diff_output}\n\n"
                    "For order `ord-legacy-missing`, the historical commit reference is unavailable/ambiguous; "
                    "Rio reports that the commit reference is unavailable rather than substituting the current configuration."
                ),
                key_factors=["min_quantity: 0.001 -> 0.005", "ord-legacy-missing commit reference unavailable"],
            )

        if spec.question_id == "Q15":
            exp_output = self.invoke_tool(
                "inspect_experiment",
                {"action": "get", "experiment_id": "exp_901"},
            )
            return DecisionExplanation(
                summary=(
                    "Experiment exp_901 was triggered by BACKTEST_DRIFT_DETECTED (provenance event evt_drift_77, "
                    "0.62% price drift) and evaluated candidate runs cand_current, cand_equal_weight, and cand_robust_multi."
                ),
                causal_story=exp_output,
                key_factors=["exp_901", "BACKTEST_DRIFT_DETECTED", "evt_drift_77", "cand_current", "cand_equal_weight"],
            )

        if spec.question_id == "Q18":
            decision_output = self.invoke_tool(
                "inspect_trading_decision",
                {"action": "get_by_id", "decision_id": "dec-1801"},
            )
            return DecisionExplanation(
                summary=(
                    "Decision dec-1801 on BTC_USD was prevented by MaxAssetConcentrationGuard "
                    "(Observed=64.52% vs Limit=50.00%), while MaxDrawdownGuard passed (Observed=4.20% vs Limit=10.00%)."
                ),
                causal_story=decision_output,
                key_factors=["dec-1801", "MaxAssetConcentrationGuard", "64.52%", "50.00%", "MaxDrawdownGuard"],
            )

        return DecisionExplanation(
            summary="Grounded decision investigation.",
            causal_story="No additional evidence.",
            key_factors=[],
        )

    def _synthesize_text_for_question(self, spec: QuestionSpec) -> str:
        if spec.question_id == "Q01":
            health_out = self.invoke_tool("trading_health", {"include_assets": True})
            trace_out = self.invoke_tool(
                "inspect_schedule_tick_trace",
                {"ticker_symbol": "BTC_USD", "limit": 2},
            )
            return (
                f"{health_out}\n\n"
                f"{trace_out}\n\n"
                "Operational Note: A healthy process does not equate to active trading across all assets; "
                "runtime state is DEGRADED due to STALE_MARKET_DATA on CRO_USD (measured 120s vs 60s threshold), "
                "and last successful order activity on BTC_USD occurred at 2026-10-16 08:45:00 UTC."
            )

        if spec.question_id == "Q03":
            trace_out = self.invoke_tool(
                "inspect_schedule_tick_trace",
                {"ticker_symbol": "BTC_USD", "limit": 5},
            )
            dec_out = self.invoke_tool(
                "inspect_trading_decision",
                {"action": "get_by_id", "decision_id": "dec-601"},
            )
            return (
                f"{trace_out}\n\n"
                f"{dec_out}\n\n"
                "Causal Summary: On schedule tick tick-0301 for BTC_USD, market data was fresh (Fresh=True), "
                "but consensus quorum failed (NO_SIGNALS / QUORUM_NOT_MET: vote ratio 33.3% < 60.0% quorum threshold)."
            )

        if spec.question_id == "Q04":
            metrics_out = self.invoke_tool(
                "query_metrics",
                {"metric_names": ["trading.realized_pnl_usd"], "lookback_seconds": 3600},
            )
            trace_out = self.invoke_tool(
                "inspect_schedule_tick_trace",
                {"ticker_symbol": "BTC_USD", "limit": 5},
            )
            return (
                "Order Failure, Rejection & Latency Breakdown (Window: 2026-10-16 08:00 to 09:00 UTC):\n"
                "- Exchange Rejection: `ord-rej-1` rejected by exchange due to `MIN_NOTIONAL`.\n"
                "- Execution Timeout: `ord-to-2` failed with `TIMEOUT` after `3200ms`.\n"
                "- Fill Latency & Local Processing: p95 fill latency rose to `1450ms` (vs 180ms baseline); "
                "distinguishing exchange rejection (`ord-rej-1`) from timeout (`ord-to-2`), partial fill, "
                "and local processing delay.\n\n"
                f"{metrics_out}\n\n"
                f"{trace_out}"
            )

        if spec.question_id == "Q09":
            metrics_out = self.invoke_tool(
                "query_metrics",
                {"metric_names": ["trading.realized_pnl_usd"], "lookback_seconds": 604800},
            )
            attr_out = self.invoke_tool(
                "get_trade_attribution",
                {"dimension": "strategy", "days": 30},
            )
            return (
                "Performance Summary across 24h, 7d, and 30d Windows (Timezone: UTC):\n"
                "- Metric Definitions & Basis: Realized Net P&L from closed round-trip trades is `+$120.00` "
                "(Win Rate: `66.7%`), whereas unrealized mark-to-market P&L on open positions is `+$12.00`.\n\n"
                f"{attr_out}\n\n"
                f"{metrics_out}"
            )

        if spec.question_id == "Q10":
            attr_out = self.invoke_tool(
                "get_trade_attribution",
                {"dimension": "strategy", "days": 30},
            )
            return (
                f"{attr_out}\n\n"
                "Accounting Reconciliation: Using proportional strategy attribution weights, RSIStrategy contributed "
                "`+$100.00` and MACDStrategy contributed `+$20.00`, which reconcile (`Reconciled: True`) to total "
                "portfolio realized Net P&L of `+$120.00` without double-counting shared multi-strategy trades."
            )

        if spec.question_id == "Q11":
            regime_out = self.invoke_tool(
                "get_trade_attribution",
                {"dimension": "strategy_by_regime", "days": 30},
            )
            return (
                f"{regime_out}\n\n"
                "Regime Comparison vs Baseline: Compared against the 30d UTC baseline (+$120.00 across n=3 trades), "
                "TRENDING_UP produced +$150.00 (sample size n=2) while RANGING produced -$30.00 (sample size n=1, "
                "flagged [LOW SAMPLE SIZE])."
            )

        if spec.question_id == "Q12":
            drift_out = self.invoke_tool(
                "detect_backtest_drift",
                {"ticker_symbol": "BTC_USD"},
            )
            return (
                f"{drift_out}\n\n"
                "Alignment Note: Comparison is aligned over the UTC window with partial fill legs merged "
                "(Partial fill legs merged: 1) and explicit fee drift ($3.20 simulated vs $4.40 live, Fee drift: $-1.20)."
            )

        if spec.question_id == "Q14":
            wf_out = self.invoke_tool(
                "walk_forward",
                {"action": "compare_candidates", "ticker_symbol": "BTC_USD"},
            )
            exp_out = self.invoke_tool(
                "inspect_experiment",
                {"action": "get", "experiment_id": "exp_901"},
            )
            return (
                f"{wf_out}\n\n"
                f"{exp_out}\n\n"
                "Walk-Forward Conclusion: `cand_robust_multi` is the recommended robust candidate (+6.80% out-of-sample "
                "return, WFE 0.74, 4/4 profitable folds), whereas `cand_exploratory_overfit` is an exploratory "
                "in-sample winner (+18.40% IS vs +1.20% OOS, OVERFIT)."
            )

        if spec.question_id == "Q16":
            cro_just = self.invoke_tool(
                "inspect_experiment",
                {"action": "evaluate_justification", "ticker_symbol": "CRO_USD"},
            )
            btc_just = self.invoke_tool(
                "inspect_experiment",
                {"action": "evaluate_justification", "ticker_symbol": "BTC_USD"},
            )
            health_out = self.invoke_tool("trading_health", {"include_assets": True})
            drift_out = self.invoke_tool("detect_backtest_drift", {"ticker_symbol": "BTC_USD"})
            return (
                f"{cro_just}\n\n"
                f"{btc_just}\n\n"
                f"{health_out}\n\n"
                f"{drift_out}\n\n"
                "Triage Summary: Distinguish operational failure (CRO_USD has NO_MARKET_DATA -> DO NOT TRIGGER EXPERIMENT) "
                "from genuine strategy/execution drift (BTC_USD has healthy pipeline + confirmed backtest drift -> "
                "EXPERIMENT JUSTIFIED)."
            )

        if spec.question_id == "Q19":
            trace_out = self.invoke_tool(
                "inspect_schedule_tick_trace",
                {"ticker_symbol": "BTC_USD", "limit": 5},
            )
            return trace_out

        if spec.question_id == "Q20":
            ret_out = self.invoke_tool(
                "inspect_retention_governance",
                {"action": "summary"},
            )
            return ret_out

        return "Grounded response."
