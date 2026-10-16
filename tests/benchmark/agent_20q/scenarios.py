from __future__ import annotations
# pylint: disable=line-too-long,too-many-lines,duplicate-code

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import os
import tempfile
from typing import Any
from unittest.mock import MagicMock

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import OrderStatus, TradeAction
from api.interfaces.account_balance import AccountBalance
from src.agent.actions import AgentActionService, AgentApprovalService
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.router.models import AgentIntent
from src.backtest.analysis.drift_detector import BacktestDriftDetector, DriftReport
from src.backtest.domain.metrics import BacktestSummary
from src.core.interfaces.database_manager import DatabaseManager
from src.events.message_event_bus import MessageEventBus
from src.exchange.interfaces.exchange_rest_manager import (
    ExchangeProvidersEnum,
    ExchangeRestManager,
)
from src.llm.tools import (
    AccountBalanceTool,
    BacktestDriftTool,
    BacktestTool,
    ConfigurationHistoryTool,
    ConfigurationTool,
    DecisionInspectorTool,
    ExchangeReadOnlyTool,
    ExperimentInspectorTool,
    GetOpenOrdersTool,
    MetricsTool,
    PortfolioSummaryTool,
    RetentionGovernanceTool,
    ScheduleTickTrace,
    ScheduleTickTracer,
    TickTraceTool,
    TradeAttributionTool,
)
from src.llm.tools.trading_health_tool import TradingHealthTool
from src.llm.tools.walk_forward_tool import WalkForwardTool
from src.metrics.services.metric_service import MetricService
from src.retention.models import (
    CategoryOutcome,
    DataCategory,
    RetentionMode,
    RetentionRun,
    RetentionRunStatus,
    RetentionTrigger,
    SkipReason,
)
from src.server.services.walk_forward_application_service import WalkForwardApplicationService
from src.server.timeline_projector import TimelineProjector
from src.trading.accounts.account_manager import AccountManager
from src.trading.activity.asset_activity_tracker import AssetActivityTracker
from src.trading.orders.order_manager import OrderManager
from src.trading.decision.decision_manager import DecisionManager
from src.trading.decision.trading_decision import (
    ConsensusSnapshot,
    DecisionStatus,
    GuardCheckResult,
    HealthEvaluation,
    MarketSnapshot,
    PortfolioSnapshot,
    RegimeSnapshot,
    RiskEvaluation,
    SizingSnapshot,
    TradingDecision,
)
from src.trading.events import (
    MarketDataEvent,
    OrderFilledEvent,
    OrderSubmittedEvent,
    SignalGeneratedEvent,
    StrategyEvaluatedEvent,
)
from src.core.severity import Severity
from src.trading.health import (
    ActiveCondition,
    HealthScope,
    ScopeType,
    TradingHealthCondition,
    TradingHealthSnapshot,
    TradingHealthState,
    TradingPermission,
)
from src.trading.protection.portfolio_risk_manager import PortfolioRiskManager
from src.vcs.application.service import VCSService
from tests.benchmark.agent_20q.models import QuestionCategory, QuestionSpec
from tests.unit.api_server.helpers import make_db_manager


TWENTY_QUESTIONS: list[QuestionSpec] = [
    QuestionSpec(
        question_id="Q01",
        number=1,
        category=QuestionCategory.LIVE_OPERATIONS,
        canonical_prompt="Is Rio healthy and currently trading?",
        paraphrases=[
            "Check Rio's operational health and tell me if it is actively trading right now.",
            "What is the current health state of the bot, any unhealthy checks, and last trading activity?",
        ],
        expected_intents=[AgentIntent.RUNTIME_DEBUG, AgentIntent.GENERAL],
        expected_tools=["trading_health", "inspect_schedule_tick_trace"],
        required_facts=["DEGRADED", "STALE_MARKET_DATA", "CRO_USD", "120", "60", "2026-10-16 08:45:00 UTC"],
        required_epistemic_phrases=["healthy process", "not equate", "last successful"],
        forbidden_hallucinations=["all subsystems healthy", "fully healthy and trading all assets"],
        baseline_readiness="Good foundation",
    ),
    QuestionSpec(
        question_id="Q02",
        number=2,
        category=QuestionCategory.LIVE_OPERATIONS,
        canonical_prompt="What are my current balances, available cash, and open orders?",
        paraphrases=[
            "Show my live exchange balances, reserved order cash, available cash, and open orders.",
            "How much cash and balance do I have on the exchange vs locally reserved in open orders?",
        ],
        expected_intents=[AgentIntent.PORTFOLIO_REVIEW, AgentIntent.GENERAL],
        expected_tools=["exchange_read_api", "portfolio_summary", "get_open_orders"],
        required_facts=["4400", "2900", "1500", "ord-101", "ord-102", "0.125"],
        required_epistemic_phrases=["exchange balance", "reserved", "locally"],
        forbidden_hallucinations=["no open orders", "available cash: $4400"],
        baseline_readiness="Good foundation",
    ),
    QuestionSpec(
        question_id="Q03",
        number=3,
        category=QuestionCategory.LIVE_OPERATIONS,
        canonical_prompt="Why hasn't BTC_USD placed an order recently?",
        paraphrases=[
            "Investigate why BTC_USD has not submitted any recent orders despite ticks running.",
            "What stage of the BTC_USD schedule tick pipeline prevented an order from being placed?",
        ],
        expected_intents=[AgentIntent.RUNTIME_DEBUG, AgentIntent.DECISION_INVESTIGATION, AgentIntent.GENERAL],
        expected_tools=["inspect_schedule_tick_trace", "inspect_trading_decision"],
        required_facts=["tick-0301", "BTC_USD", "Fresh=True", "33.3%", "60.0%", "NO_SIGNALS", "QUORUM_NOT_MET"],
        required_epistemic_phrases=["market data", "consensus", "quorum"],
        forbidden_hallucinations=["exchange API down", "stale market data on BTC_USD"],
        baseline_readiness="Partial",
    ),
    QuestionSpec(
        question_id="Q04",
        number=4,
        category=QuestionCategory.LIVE_OPERATIONS,
        canonical_prompt="Are orders failing, being rejected, or taking longer to execute?",
        paraphrases=[
            "Check for recent order rejections, execution timeouts, partial fills, or latency spikes.",
            "Have any orders failed or slowed down recently? Distinguish exchange rejections from timeouts.",
        ],
        expected_intents=[AgentIntent.RUNTIME_DEBUG, AgentIntent.PERFORMANCE_ANALYSIS, AgentIntent.GENERAL],
        expected_tools=["query_metrics", "inspect_schedule_tick_trace"],
        required_facts=["ord-rej-1", "MIN_NOTIONAL", "ord-to-2", "3200ms", "1450ms", "2026-10-16 08:00"],
        required_epistemic_phrases=["exchange rejection", "timeout", "partial fill", "local processing"],
        forbidden_hallucinations=["zero order failures", "all orders completed normally"],
        baseline_readiness="Good foundation",
    ),
    QuestionSpec(
        question_id="Q05",
        number=5,
        category=QuestionCategory.DECISIONS_CONFIG,
        canonical_prompt="Why did Rio buy or sell this asset?",
        paraphrases=[
            "Explain the recorded trading decision, votes, sizing, and risk checks for order ord-501 on BTC_USD.",
            "Why did Rio execute the BTC_USD BUY order ord-501 (decision dec-501)?",
        ],
        expected_intents=[AgentIntent.DECISION_INVESTIGATION, AgentIntent.GENERAL],
        expected_tools=["inspect_trading_decision"],
        required_facts=["dec-501", "ord-501", "RSIStrategy", "MACDStrategy", "0.05 * available_cash / close_price", "0.025"],
        required_epistemic_phrases=["recorded", "evidence", "consensus", "sizing"],
        forbidden_hallucinations=["news sentiment triggered", "manual override"],
        baseline_readiness="Good foundation",
    ),
    QuestionSpec(
        question_id="Q06",
        number=6,
        category=QuestionCategory.DECISIONS_CONFIG,
        canonical_prompt="Why was a particular strategy's signal rejected?",
        paraphrases=[
            "In decision dec-601, why was BollingerStrategy's BUY signal rejected?",
            "Check the persisted rejection reason for BollingerStrategy on BTC_USD decision dec-601.",
        ],
        expected_intents=[AgentIntent.DECISION_INVESTIGATION, AgentIntent.GENERAL],
        expected_tools=["inspect_trading_decision"],
        required_facts=["dec-601", "BollingerStrategy", "0.25", "60.0%", "QUORUM_NOT_MET"],
        required_epistemic_phrases=["persisted", "rejection reason", "quorum"],
        forbidden_hallucinations=["rejected by drawdown guard", "inferred after the fact"],
        baseline_readiness="Partial",
    ),
    QuestionSpec(
        question_id="Q07",
        number=7,
        category=QuestionCategory.DECISIONS_CONFIG,
        canonical_prompt="What changed between the current configuration and the configuration used for this order?",
        paraphrases=[
            "Compare the current HEAD configuration against the commit used for order ord-501 and order ord-legacy-missing.",
            "What configuration parameters changed since order ord-501 (and what if an order's commit ref is missing)?",
        ],
        expected_intents=[AgentIntent.DECISION_INVESTIGATION, AgentIntent.CONFIGURATION, AgentIntent.GENERAL],
        expected_tools=["get_configuration_history", "get_configuration", "inspect_trading_decision"],
        required_facts=["min_quantity", "0.001", "0.005", "ord-legacy-missing", "unavailable"],
        required_epistemic_phrases=["commit reference", "unavailable", "rather than substituting"],
        forbidden_hallucinations=["ord-legacy-missing used the current HEAD config without changes"],
        baseline_readiness="Good foundation",
    ),
    QuestionSpec(
        question_id="Q08",
        number=8,
        category=QuestionCategory.DECISIONS_CONFIG,
        canonical_prompt="What configuration change do you recommend, and why?",
        paraphrases=[
            "Propose a validated configuration change for ETH_USD to fix minimum quantity rejections.",
            "Recommend a configuration adjustment with diff and rationale for ETH_USD.",
        ],
        expected_intents=[AgentIntent.CONFIGURATION],
        expected_tools=["get_configuration"],
        required_facts=["ETH_USD", "min_quantity", "0.0001", "0.001"],
        required_epistemic_phrases=["hypothesis", "approval", "not proof"],
        forbidden_hallucinations=["already applied to live production without approval", "guaranteed profit"],
        baseline_readiness="Implemented with guardrails",
    ),
    QuestionSpec(
        question_id="Q09",
        number=9,
        category=QuestionCategory.PERFORMANCE_ATTRIBUTION,
        canonical_prompt="How has the bot performed over the last 24 hours, 7 days, or 30 days?",
        paraphrases=[
            "Report Rio's trading performance across the 24h, 7d, and 30d UTC windows.",
            "What are the realized and mark-to-market performance metrics over 24 hours, 7 days, and 30 days?",
        ],
        expected_intents=[AgentIntent.PERFORMANCE_ANALYSIS],
        expected_tools=["query_metrics", "get_trade_attribution"],
        required_facts=["+$120.00", "66.7%", "UTC", "24h", "7d", "30d"],
        required_epistemic_phrases=["UTC", "realized", "mark-to-market"],
        forbidden_hallucinations=["+$5000.00", "100% win rate"],
        baseline_readiness="Good foundation",
    ),
    QuestionSpec(
        question_id="Q10",
        number=10,
        category=QuestionCategory.PERFORMANCE_ATTRIBUTION,
        canonical_prompt="Which strategies contributed most to profit or loss?",
        paraphrases=[
            "Rank strategies by profit and loss contribution and verify reconciliation to net P&L.",
            "Show proportional strategy P&L attribution and confirm multi-strategy trades are not double-counted.",
        ],
        expected_intents=[AgentIntent.PERFORMANCE_ANALYSIS],
        expected_tools=["get_trade_attribution"],
        required_facts=["RSIStrategy", "+$100.00", "MACDStrategy", "+$20.00", "+$120.00", "Reconciled: True"],
        required_epistemic_phrases=["reconcile", "proportional", "double"],
        forbidden_hallucinations=["total portfolio net PnL is +$220.00"],
        baseline_readiness="Partial — validate accounting",
    ),
    QuestionSpec(
        question_id="Q11",
        number=11,
        category=QuestionCategory.PERFORMANCE_ATTRIBUTION,
        canonical_prompt="Has strategy performance changed by market regime?",
        paraphrases=[
            "Compare strategy P&L and win rate across market regimes with sample sizes and baseline.",
            "How have RSIStrategy and MACDStrategy performed in TRENDING_UP vs RANGING regimes?",
        ],
        expected_intents=[AgentIntent.PERFORMANCE_ANALYSIS],
        expected_tools=["get_trade_attribution"],
        required_facts=["TRENDING_UP", "RANGING", "+$150.00", "-$30.00", "n=2", "n=1", "LOW SAMPLE SIZE"],
        required_epistemic_phrases=["sample size", "regime", "baseline"],
        forbidden_hallucinations=["RANGING regime has a large statistically significant sample of 500 trades"],
        baseline_readiness="Partial",
    ),
    QuestionSpec(
        question_id="Q12",
        number=12,
        category=QuestionCategory.PERFORMANCE_ATTRIBUTION,
        canonical_prompt="Is the bot's live execution diverging from its backtest?",
        paraphrases=[
            "Check if BTC_USD live execution has drifted from its backtest replay.",
            "Compare simulated fills vs live fills for BTC_USD including partial fills, fees, and time alignment.",
        ],
        expected_intents=[AgentIntent.BACKTEST, AgentIntent.PERFORMANCE_ANALYSIS, AgentIntent.GENERAL],
        expected_tools=["detect_backtest_drift"],
        required_facts=["BTC_USD", "Simulated fills: 5", "Live fills: 4", "Partial fill legs merged: 1", "395.00", "-1.20", "Drifted: True"],
        required_epistemic_phrases=["Aligned Window", "partial fill", "fee"],
        forbidden_hallucinations=["Drifted: False", "zero execution divergence"],
        baseline_readiness="Partial",
    ),
    QuestionSpec(
        question_id="Q13",
        number=13,
        category=QuestionCategory.BACKTESTING_EXPERIMENTS,
        canonical_prompt="Would this strategy have been profitable on historical data?",
        paraphrases=[
            "Run a historical backtest on BTC_USD from 2026-09-01 to 2026-10-01 and report return, drawdown, and trade count.",
            "How did the BTC_USD strategy perform on historical data between 2026-09-01 and 2026-10-01?",
        ],
        expected_intents=[AgentIntent.BACKTEST],
        expected_tools=["backtest"],
        required_facts=["BTC_USD", "2026-09-01", "2026-10-01", "10000", "0.1%", "+6.40%", "-3.10%", "28"],
        required_epistemic_phrases=["drawdown", "trades", "fee", "starting capital"],
        forbidden_hallucinations=["zero drawdown", "guaranteed future return"],
        baseline_readiness="Implemented",
    ),
    QuestionSpec(
        question_id="Q14",
        number=14,
        category=QuestionCategory.BACKTESTING_EXPERIMENTS,
        canonical_prompt="Which candidate configuration performs best in walk-forward validation?",
        paraphrases=[
            "Compare the walk-forward validation candidates for BTC_USD across folds and out-of-sample periods.",
            "Which candidate configuration is robust vs overfit in walk-forward validation for BTC_USD?",
        ],
        expected_intents=[AgentIntent.BACKTEST, AgentIntent.PERFORMANCE_ANALYSIS, AgentIntent.GENERAL],
        expected_tools=["walk_forward", "inspect_experiment"],
        required_facts=["cand_robust_multi", "cand_exploratory_overfit", "+6.80%", "0.74", "ROBUST", "OVERFIT", "4/4"],
        required_epistemic_phrases=["out-of-sample", "fold", "exploratory", "robust"],
        forbidden_hallucinations=["promote cand_exploratory_overfit because its in-sample return is +18.40%"],
        baseline_readiness="Partial",
    ),
    QuestionSpec(
        question_id="Q15",
        number=15,
        category=QuestionCategory.BACKTESTING_EXPERIMENTS,
        canonical_prompt="Why did this experiment run, and what triggered it?",
        paraphrases=[
            "Explain the trigger provenance, causal evidence, and candidate runs for experiment exp_901.",
            "What event triggered experiment exp_901 and which candidate runs were bound to it?",
        ],
        expected_intents=[AgentIntent.DECISION_INVESTIGATION, AgentIntent.BACKTEST, AgentIntent.GENERAL],
        expected_tools=["inspect_experiment"],
        required_facts=["exp_901", "BACKTEST_DRIFT_DETECTED", "evt_drift_77", "0.62%", "cand_current", "cand_equal_weight"],
        required_epistemic_phrases=["triggered", "provenance", "candidate"],
        forbidden_hallucinations=["manually triggered by an unknown user without evidence"],
        baseline_readiness="Partial",
    ),
    QuestionSpec(
        question_id="Q16",
        number=16,
        category=QuestionCategory.BACKTESTING_EXPERIMENTS,
        canonical_prompt="Has the bot become inactive or drifted enough to justify a new experiment?",
        paraphrases=[
            "Evaluate whether CRO_USD inactivity and BTC_USD drift justify triggering a new experiment.",
            "Should we launch a research experiment for CRO_USD or BTC_USD right now?",
        ],
        expected_intents=[AgentIntent.RUNTIME_DEBUG, AgentIntent.BACKTEST, AgentIntent.GENERAL],
        expected_tools=["inspect_experiment", "trading_health", "detect_backtest_drift"],
        required_facts=["CRO_USD", "NO_MARKET_DATA", "DO NOT TRIGGER EXPERIMENT", "BTC_USD", "EXPERIMENT JUSTIFIED"],
        required_epistemic_phrases=["operational failure", "strategy", "drift"],
        forbidden_hallucinations=["launch a strategy optimization experiment for CRO_USD to fix the stalled market data feed"],
        baseline_readiness="Partial",
    ),
    QuestionSpec(
        question_id="Q17",
        number=17,
        category=QuestionCategory.RISK_TRACE_GOVERNANCE,
        canonical_prompt="What is my current portfolio exposure, drawdown, and concentration risk?",
        paraphrases=[
            "Report my USD portfolio exposure, drawdown, single-asset concentration, reserved orders, and missing price data.",
            "Check portfolio drawdown and asset concentration limits on CRYPTO_DOT_COM.",
        ],
        expected_intents=[AgentIntent.PORTFOLIO_REVIEW, AgentIntent.RISK_ANALYSIS],
        expected_tools=["portfolio_summary", "exchange_read_api"],
        required_facts=["2026-10-16T09:00:00Z", "USD", "64.52%", "50%", "4.2%", "10%", "ord-101", "SOL_USD", "PRICE UNAVAILABLE"],
        required_epistemic_phrases=["Valuation Timestamp", "concentration", "Unavailable Price Data"],
        forbidden_hallucinations=["SOL_USD market price is $150.00", "all asset prices are available"],
        baseline_readiness="Good foundation",
    ),
    QuestionSpec(
        question_id="Q18",
        number=18,
        category=QuestionCategory.RISK_TRACE_GOVERNANCE,
        canonical_prompt="Why did the risk manager or guard prevent a trade?",
        paraphrases=[
            "Inspect decision dec-1801 and explain which risk guard blocked the BTC_USD trade and what the exact limits were.",
            "Why was the BTC_USD BUY trade in decision dec-1801 prevented by the risk manager?",
        ],
        expected_intents=[AgentIntent.DECISION_INVESTIGATION, AgentIntent.RISK_ANALYSIS, AgentIntent.GENERAL],
        expected_tools=["inspect_trading_decision"],
        required_facts=["dec-1801", "MaxAssetConcentrationGuard", "64.52%", "50.00%", "MaxDrawdownGuard", "4.20%", "10.00%"],
        required_epistemic_phrases=["Observed", "Limit", "MaxAssetConcentrationGuard"],
        forbidden_hallucinations=["blocked by MaxDrawdownGuard exceeding 10%"],
        baseline_readiness="Partial",
    ),
    QuestionSpec(
        question_id="Q19",
        number=19,
        category=QuestionCategory.RISK_TRACE_GOVERNANCE,
        canonical_prompt="What happened during this run, from schedule tick through order execution?",
        paraphrases=[
            "Trace schedule tick tick-1901 end-to-end from tick start through strategy evaluation, risk check, order fill, and reconciliation.",
            "Show the complete causal trace for tick-1901 and contrast it with no-order tick tick-0301.",
        ],
        expected_intents=[AgentIntent.RUNTIME_DEBUG, AgentIntent.DECISION_INVESTIGATION, AgentIntent.GENERAL],
        expected_tools=["inspect_schedule_tick_trace"],
        required_facts=["tick-1901", "Market Data Check", "Strategy Evaluations", "Consensus Evaluation", "Risk & Guard Check", "ord-501", "230ms", "Reconciled=True", "tick-0301", "NO_ORDER"],
        required_epistemic_phrases=["Market Data Check", "Consensus Evaluation", "Reconciliation", "NO_ORDER"],
        forbidden_hallucinations=["tick-0301 placed an order on the exchange"],
        baseline_readiness="Partial — important gap",
    ),
    QuestionSpec(
        question_id="Q20",
        number=20,
        category=QuestionCategory.RISK_TRACE_GOVERNANCE,
        canonical_prompt="What data will expire, what will be retained, and why was a record deleted or skipped?",
        paraphrases=[
            "Inspect data retention policies, dry-run expiration preview, completed deletions in ret_run_01, and skip reasons.",
            "What records are scheduled to expire vs already deleted in retention run ret_run_01, and why were records skipped?",
        ],
        expected_intents=[AgentIntent.SYSTEM_HELP, AgentIntent.RUNTIME_DEBUG, AgentIntent.GENERAL],
        expected_tools=["inspect_retention_governance"],
        required_facts=["MARKET_DATA", "30d", "FINANCIAL", "365d", "1200", "ret_run_01", "800", "RETENTION_HOLD", "hold_audit_1", "DEPENDENCY_REFERENCED"],
        required_epistemic_phrases=["Configured Retention Policies", "Dry-Run Expiration Preview", "EXECUTED RUN", "Skip Reasons"],
        forbidden_hallucinations=["all 1200 previewed records have already been permanently deleted"],
        baseline_readiness="Partial — recently added",
    ),
]


@dataclass
class SeededBenchmarkEnvironment:  # pylint: disable=too-many-instance-attributes
    db_manager: DatabaseManager
    vcs: VCSService
    commit_v1: str
    commit_v2: str
    decision_manager: DecisionManager
    portfolio_risk_manager: PortfolioRiskManager
    health_monitor: Any
    activity_tracker: AssetActivityTracker
    tick_tracer: ScheduleTickTracer
    tools: dict[str, Any]
    timeline_projector: TimelineProjector
    approval_service: AgentApprovalService


def build_seeded_environment(tmp_db_path: str | None = None) -> SeededBenchmarkEnvironment:  # pylint: disable=too-many-locals,too-many-statements
    if tmp_db_path is None:
        tmp_db_path = os.path.join(tempfile.mkdtemp(prefix="rio_20q_"), "benchmark.sqlite")
    db = make_db_manager(tmp_db_path)
    vcs = VCSService(db)

    config_v1 = {
        "assets": [
            {
                "base_ticker_symbol": "BTC",
                "quote_ticker_symbol": "USD",
                "name": "Bitcoin",
                "exchange": "CRYPTO_DOT_COM",
                "min_quantity": 0.001,
                "quote_decimals": 2,
                "quantity_decimals": 4,
                "schedule": 1,
                "candles_timeframe": "MIN1",
                "enabled": True,
            },
            {
                "base_ticker_symbol": "ETH",
                "quote_ticker_symbol": "USD",
                "name": "Ethereum",
                "exchange": "CRYPTO_DOT_COM",
                "min_quantity": 0.0001,
                "quote_decimals": 2,
                "quantity_decimals": 3,
                "schedule": 1,
                "candles_timeframe": "MIN1",
                "enabled": True,
            },
            {
                "base_ticker_symbol": "CRO",
                "quote_ticker_symbol": "USD",
                "name": "Cronos",
                "exchange": "CRYPTO_DOT_COM",
                "min_quantity": 1.0,
                "quote_decimals": 4,
                "quantity_decimals": 1,
                "schedule": 1,
                "candles_timeframe": "MIN1",
                "enabled": True,
            },
        ]
    }
    c1 = vcs.seed_if_empty(config_v1, author="system", message="Initial seed config v1")
    commit_v1 = c1.hash

    config_v2 = {
        "assets": [
            {
                **config_v1["assets"][0],
                "min_quantity": 0.005,
            },
            config_v1["assets"][1],
            config_v1["assets"][2],
        ]
    }
    c2 = vcs.commit(
        content=config_v2,
        author="operator",
        message="Increase BTC_USD min_quantity from 0.001 to 0.005",
    )
    commit_v2 = c2.hash

    bus = MessageEventBus()
    timeline_projector = TimelineProjector(event_bus=bus, db_manager=db, flush_interval_seconds=0)
    config_service = ConfigurationService(vcs=vcs)
    action_service = AgentActionService(event_bus=bus)
    approval_service = AgentApprovalService(
        vcs=vcs,
        configuration_service=config_service,
        action_service=action_service,
        event_bus=bus,
    )

    health_monitor = MagicMock()
    health_monitor.snapshot = TradingHealthSnapshot(
        state=TradingHealthState.DEGRADED,
        version=4,
        effective_permissions=frozenset({
            TradingPermission.NEW_ORDERS,
            TradingPermission.CANCEL_ORDERS,
            TradingPermission.REDUCE_POSITIONS,
        }),
        active_conditions=(
            ActiveCondition(
                condition=TradingHealthCondition.MARKET_DATA_STALE,
                scope=HealthScope(scope_type=ScopeType.ASSET, identifier="CRO_USD"),
                severity=Severity.WARNING,
                measured_value="120s",
                threshold="60s",
                consecutive_healthy_checks=0,
                first_detected_at=datetime(2026, 10, 16, 8, 58, 0, tzinfo=timezone.utc),
                last_observed_at=datetime(2026, 10, 16, 9, 0, 0, tzinfo=timezone.utc),
            ),
        ),
        updated_at=datetime(2026, 10, 16, 9, 0, 0, tzinfo=timezone.utc),
    )

    activity_tracker = AssetActivityTracker()
    activity_tracker.subscribe(bus)
    ts_last_btc = datetime(2026, 10, 16, 8, 45, 0, tzinfo=timezone.utc).timestamp()
    bus.publish(MarketDataEvent(
        ticker_symbol="BTC_USD",
        market_data=MarketData(
            volume=Decimal("10"),
            high_price=Decimal("64500"),
            low_price=Decimal("63500"),
            close_price=Decimal("64000"),
            timestamp=ts_last_btc,
        ),
    ))
    bus.publish(StrategyEvaluatedEvent(symbol="BTC_USD", evaluated_at=ts_last_btc))
    bus.publish(SignalGeneratedEvent(symbol="BTC_USD", action="BUY", generated_at=ts_last_btc))
    ord_501 = Order(
        uuid="ord-501",
        provider_name="CRYPTO_DOT_COM",
        ticker_symbol="BTC_USD",
        price=Decimal("64000"),
        fill_price=Decimal("64000"),
        quantity="0.025",
        trade_action=TradeAction.BUY,
        created_time=ts_last_btc,
        executed_time=ts_last_btc,
        status=OrderStatus.COMPLETED,
        commit_hash=commit_v1,
    )
    bus.publish(OrderSubmittedEvent(symbol="BTC_USD", order=ord_501))
    bus.publish(OrderFilledEvent(symbol="BTC_USD", order=ord_501))

    portfolio_risk_manager = PortfolioRiskManager(
        max_portfolio_drawdown=Decimal("10"),
        max_asset_concentration=Decimal("50"),
    )
    portfolio = portfolio_risk_manager.get_portfolio("CRYPTO_DOT_COM", "USD")
    portfolio.valuation_timestamp = "2026-10-16T09:00:00Z"
    portfolio.update_cash(Decimal("4400"))
    portfolio.reserve_cash("ord-101", Decimal("1000"))
    portfolio.reserve_cash("ord-102", Decimal("500"))
    portfolio.update_asset_position("BTC_USD", Decimal("0.125"))
    portfolio.update_asset_mark_price("BTC_USD", Decimal("64000"))
    portfolio.update_asset_position("SOL_USD", Decimal("10"))
    portfolio.peak_equity = Decimal("12943.63")

    rest_manager = MagicMock(spec=ExchangeRestManager)
    rest_manager.get_account_balance.return_value = [
        AccountBalance(currency="USD", available_balance=Decimal("4400")),
        AccountBalance(currency="BTC", available_balance=Decimal("0.125")),
        AccountBalance(currency="SOL", available_balance=Decimal("10")),
    ]
    rest_manager.get_market_data.return_value = MarketData(
        volume=Decimal("125.4"),
        high_price=Decimal("64800"),
        low_price=Decimal("63200"),
        close_price=Decimal("64000"),
        timestamp=ts_last_btc,
    )
    rest_manager.get_candles.return_value = [
        Candle(
            open=Decimal("63900"),
            high=Decimal("64100"),
            low=Decimal("63850"),
            close=Decimal("64000"),
            volume=Decimal("12.5"),
            start_time=int(ts_last_btc),
        )
    ]

    open_orders_list = [
        Order(
            uuid="ord-101",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("62000"),
            quantity="0.0161",
            trade_action=TradeAction.BUY,
            created_time=ts_last_btc,
            status=OrderStatus.PENDING,
        ),
        Order(
            uuid="ord-102",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="ETH_USD",
            price=Decimal("2500"),
            quantity="0.200",
            trade_action=TradeAction.BUY,
            created_time=ts_last_btc,
            status=OrderStatus.PENDING,
        ),
    ]
    order_manager = MagicMock(spec=OrderManager)
    order_manager.get_open_orders.side_effect = lambda ex, sym=None: [
        o for o in open_orders_list if sym is None or o.ticker_symbol == sym
    ]

    decision_manager = DecisionManager(database_manager=db)
    decision_manager.record_decision(
        TradingDecision(
            decision_id="dec-501",
            timestamp=ts_last_btc,
            ticker_symbol="BTC_USD",
            exchange="CRYPTO_DOT_COM",
            trade_action=TradeAction.BUY,
            status=DecisionStatus.EXECUTED,
            resulting_order_id="ord-501",
            commit_hash=commit_v1,
            winning_strategy="RSIStrategy",
            strategy_attributions={"RSIStrategy": 0.6, "MACDStrategy": 0.4},
            market_snapshot=MarketSnapshot(
                close_price=Decimal("64000"),
                bid_price=Decimal("63995"),
                ask_price=Decimal("64005"),
                spread_pct=Decimal("0.00015"),
                candles_count=100,
            ),
            regime_snapshot=RegimeSnapshot(
                regime="TRENDING_UP",
                volatility=0.018,
                trend_strength=0.62,
                spread=0.00015,
                exposure_multiplier=1.0,
            ),
            consensus_snapshot=ConsensusSnapshot(
                action=TradeAction.BUY,
                votes={"RSIStrategy": True, "MACDStrategy": True},
                weights={"RSIStrategy": 0.6, "MACDStrategy": 0.4},
                factor=1.0,
                quorum=True,
                quorum_margin=0.4,
                vote_ratio=1.0,
                winning_strategy="RSIStrategy",
                strategy_attributions={"RSIStrategy": 0.6, "MACDStrategy": 0.4},
            ),
            sizing_snapshot=SizingSnapshot(
                formula="0.05 * available_cash / close_price",
                calculated_quantity=Decimal("0.025"),
                min_quantity=Decimal("0.001"),
                final_quantity=Decimal("0.025"),
                variables={"available_cash": "32000", "close_price": "64000"},
            ),
            portfolio_snapshot=PortfolioSnapshot(
                available_cash=Decimal("2900"),
                total_equity=Decimal("12400"),
                current_exposure_pct=0.52,
                asset_exposure_pct=0.48,
                drawdown_pct=0.02,
            ),
            risk_evaluation=RiskEvaluation(
                passed=True,
                guard_evaluations=[
                    GuardCheckResult(
                        guard_name="MaxAssetConcentrationGuard",
                        passed=True,
                        observed_value="48.00%",
                        limit_value="50.00%",
                    ),
                    GuardCheckResult(
                        guard_name="MaxDrawdownGuard",
                        passed=True,
                        observed_value="2.00%",
                        limit_value="10.00%",
                    ),
                ],
            ),
            health_evaluation=HealthEvaluation(state="TRADING", allowed=True),
        )
    )

    decision_manager.record_decision(
        TradingDecision(
            decision_id="dec-601",
            timestamp=ts_last_btc + 60,
            ticker_symbol="BTC_USD",
            exchange="CRYPTO_DOT_COM",
            trade_action=TradeAction.BUY,
            status=DecisionStatus.REJECTED,
            rejection_reason="QUORUM_NOT_MET (vote_ratio 25.0% < 60.0% threshold)",
            commit_hash=commit_v2,
            market_snapshot=MarketSnapshot(close_price=Decimal("64100"), candles_count=100),
            regime_snapshot=RegimeSnapshot(regime="RANGING", volatility=0.012, trend_strength=0.05, spread=0.0002),
            consensus_snapshot=ConsensusSnapshot(
                action=TradeAction.BUY,
                votes={"BollingerStrategy": True, "RSIStrategy": False, "MACDStrategy": False},
                weights={"BollingerStrategy": 0.25, "RSIStrategy": 0.40, "MACDStrategy": 0.35},
                factor=0.60,
                quorum=False,
                quorum_margin=-0.35,
                vote_ratio=0.25,
                strategy_rejections={
                    "BollingerStrategy": "QUORUM_NOT_MET (vote_ratio 25.0% < 60.0% threshold; opposing HOLD weight 75.0%)",
                },
            ),
            sizing_snapshot=SizingSnapshot(min_quantity=Decimal("0.005")),
            portfolio_snapshot=PortfolioSnapshot(available_cash=Decimal("2900"), total_equity=Decimal("12400")),
            risk_evaluation=RiskEvaluation(passed=True),
        )
    )

    decision_manager.record_decision(
        TradingDecision(
            decision_id="dec-1801",
            timestamp=ts_last_btc + 120,
            ticker_symbol="BTC_USD",
            exchange="CRYPTO_DOT_COM",
            trade_action=TradeAction.BUY,
            status=DecisionStatus.REJECTED,
            rejection_reason="MaxAssetConcentrationGuard: Asset concentration 64.52% exceeds max_per_asset limit 50.00%",
            commit_hash=commit_v2,
            market_snapshot=MarketSnapshot(close_price=Decimal("64000"), candles_count=100),
            regime_snapshot=RegimeSnapshot(regime="TRENDING_UP", volatility=0.019, trend_strength=0.55, spread=0.0002),
            consensus_snapshot=ConsensusSnapshot(
                action=TradeAction.BUY,
                votes={"RSIStrategy": True, "MACDStrategy": True},
                weights={"RSIStrategy": 0.6, "MACDStrategy": 0.4},
                factor=0.60,
                quorum=True,
                quorum_margin=0.40,
                vote_ratio=1.0,
                winning_strategy="RSIStrategy",
            ),
            sizing_snapshot=SizingSnapshot(
                formula="0.05 * available_cash / close_price",
                calculated_quantity=Decimal("0.010"),
                min_quantity=Decimal("0.005"),
                final_quantity=Decimal("0.010"),
            ),
            portfolio_snapshot=PortfolioSnapshot(
                available_cash=Decimal("2900"),
                total_equity=Decimal("12400"),
                current_exposure_pct=0.6452,
                asset_exposure_pct=0.6452,
                drawdown_pct=0.042,
            ),
            risk_evaluation=RiskEvaluation(
                passed=False,
                effective_max_per_asset=Decimal("50.00"),
                effective_max_total=Decimal("80.00"),
                min_quote_reserve=Decimal("1000.00"),
                rejection_reason="MaxAssetConcentrationGuard: Asset concentration 64.52% exceeds max_per_asset limit 50.00%",
                guard_evaluations=[
                    GuardCheckResult(
                        guard_name="MaxAssetConcentrationGuard",
                        passed=False,
                        observed_value="64.52%",
                        limit_value="50.00%",
                        rejection_reason="Asset concentration 64.52% exceeds max_per_asset limit 50.00%",
                    ),
                    GuardCheckResult(
                        guard_name="MaxDrawdownGuard",
                        passed=True,
                        observed_value="4.20%",
                        limit_value="10.00%",
                    ),
                ],
            ),
        )
    )

    tick_tracer = ScheduleTickTracer()
    tick_tracer.record(
        ScheduleTickTrace(
            tick_id="tick-1901",
            ticker_symbol="BTC_USD",
            exchange="CRYPTO_DOT_COM",
            timestamp=ts_last_btc,
            schedule="EVERY_MINUTE",
            market_data_fresh=True,
            candle_timestamp=ts_last_btc,
            candle_age_seconds=1.2,
            close_price="64000",
            strategy_evaluations={
                "RSIStrategy": {"signal": "BUY", "weight": 0.6, "latency_ms": 12},
                "MACDStrategy": {"signal": "BUY", "weight": 0.4, "latency_ms": 15},
            },
            consensus_quorum=True,
            vote_ratio=1.0,
            quorum_threshold=0.60,
            winning_strategy="RSIStrategy",
            risk_passed=True,
            guard_evaluations=[
                {"guard_name": "MaxAssetConcentrationGuard", "passed": True},
                {"guard_name": "MaxDrawdownGuard", "passed": True},
            ],
            decision_id="dec-501",
            order_id="ord-501",
            order_status="COMPLETED",
            submitted_at=ts_last_btc + 0.05,
            filled_at=ts_last_btc + 0.28,
            execution_latency_ms=230.0,
            reconciled=True,
            reconciliation_note="Order ord-501 fill qty 0.025 matched exchange execution report",
            terminal_stage="COMPLETED",
        )
    )
    tick_tracer.record(
        ScheduleTickTrace(
            tick_id="tick-0301",
            ticker_symbol="BTC_USD",
            exchange="CRYPTO_DOT_COM",
            timestamp=ts_last_btc + 300,
            schedule="EVERY_MINUTE",
            market_data_fresh=True,
            candle_timestamp=ts_last_btc + 298,
            candle_age_seconds=2.1,
            close_price="64120",
            strategy_evaluations={
                "BollingerStrategy": {"signal": "BUY", "weight": 0.333, "latency_ms": 10},
                "RSIStrategy": {"signal": "HOLD", "weight": 0.333, "latency_ms": 11},
                "MACDStrategy": {"signal": "HOLD", "weight": 0.334, "latency_ms": 14},
            },
            consensus_quorum=False,
            vote_ratio=0.333,
            quorum_threshold=0.60,
            winning_strategy=None,
            risk_passed=None,
            terminal_stage="NO_SIGNALS",
            no_order_reason="QUORUM_NOT_MET (vote_ratio 33.3% < 60.0% quorum threshold)",
        )
    )

    assets = [
        Asset(
            base_ticker_symbol="BTC",
            quote_ticker_symbol="USD",
            name="Bitcoin",
            exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
            min_quantity=0.005,
            quote_decimals=2,
            quantity_decimals=4,
            schedule=AssetSchedule.EVERY_MINUTE,
            candles_timeframe=Timeframe.MIN1,
            enabled=True,
        ),
        Asset(
            base_ticker_symbol="ETH",
            quote_ticker_symbol="USD",
            name="Ethereum",
            exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
            min_quantity=0.0001,
            quote_decimals=2,
            quantity_decimals=3,
            schedule=AssetSchedule.EVERY_MINUTE,
            candles_timeframe=Timeframe.MIN1,
            enabled=True,
        ),
    ]

    now_ts = datetime.now(timezone.utc).timestamp()
    seeded_orders = [
        Order(
            uuid="b_multi_1",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("60000"),
            fill_price=Decimal("60000"),
            quantity="1.0",
            trade_action=TradeAction.BUY,
            status=OrderStatus.COMPLETED,
            created_time=now_ts - 7200,
            executed_time=now_ts - 7200,
            fees=Decimal("0"),
            winning_strategy="RSIStrategy",
            strategy_attributions={"RSIStrategy": 0.5, "MACDStrategy": 0.5},
            regime="TRENDING_UP",
            commit_hash=commit_v1,
        ),
        Order(
            uuid="s_multi_1",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("60100"),
            fill_price=Decimal("60100"),
            quantity="1.0",
            trade_action=TradeAction.SELL,
            status=OrderStatus.COMPLETED,
            created_time=now_ts - 6800,
            executed_time=now_ts - 6800,
            fees=Decimal("0"),
            winning_strategy="RSIStrategy",
            strategy_attributions={"RSIStrategy": 0.5, "MACDStrategy": 0.5},
            regime="TRENDING_UP",
            commit_hash=commit_v1,
        ),
        Order(
            uuid="b_rsi_2",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("61000"),
            fill_price=Decimal("61000"),
            quantity="1.0",
            trade_action=TradeAction.BUY,
            status=OrderStatus.COMPLETED,
            created_time=now_ts - 5400,
            executed_time=now_ts - 5400,
            fees=Decimal("0"),
            winning_strategy="RSIStrategy",
            strategy_attributions={"RSIStrategy": 1.0},
            regime="TRENDING_UP",
            commit_hash=commit_v1,
        ),
        Order(
            uuid="s_rsi_2",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("61050"),
            fill_price=Decimal("61050"),
            quantity="1.0",
            trade_action=TradeAction.SELL,
            status=OrderStatus.COMPLETED,
            created_time=now_ts - 5000,
            executed_time=now_ts - 5000,
            fees=Decimal("0"),
            winning_strategy="RSIStrategy",
            strategy_attributions={"RSIStrategy": 1.0},
            regime="TRENDING_UP",
            commit_hash=commit_v1,
        ),
        Order(
            uuid="b_macd_3",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("62000"),
            fill_price=Decimal("62000"),
            quantity="1.0",
            trade_action=TradeAction.BUY,
            status=OrderStatus.COMPLETED,
            created_time=now_ts - 3600,
            executed_time=now_ts - 3600,
            fees=Decimal("0"),
            winning_strategy="MACDStrategy",
            strategy_attributions={"MACDStrategy": 1.0},
            regime="RANGING",
            commit_hash=commit_v2,
        ),
        Order(
            uuid="s_macd_3",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("61970"),
            fill_price=Decimal("61970"),
            quantity="1.0",
            trade_action=TradeAction.SELL,
            status=OrderStatus.COMPLETED,
            created_time=now_ts - 3200,
            executed_time=now_ts - 3200,
            fees=Decimal("0"),
            winning_strategy="MACDStrategy",
            strategy_attributions={"MACDStrategy": 1.0},
            regime="RANGING",
            commit_hash=commit_v2,
        ),
    ]
    mock_order_db = MagicMock(spec=DatabaseManager)
    mock_uow = MagicMock()
    mock_order_repo = MagicMock()
    mock_order_repo.get_completed_by_ticker_and_executed_range.return_value = seeded_orders
    mock_order_repo.get_all.return_value = seeded_orders
    mock_uow.get_repository.return_value = mock_order_repo
    mock_uow.__enter__.return_value = mock_uow
    mock_uow.__exit__.return_value = None
    mock_order_db.get_unit_of_work.return_value = mock_uow

    metric_service = MagicMock(spec=MetricService)
    metric_service.query.return_value = [
        {
            "metric": "trading.realized_pnl_usd",
            "window": "24h / 7d / 30d UTC",
            "realized_net_pnl_usd": "+$120.00",
            "unrealized_mtm_pnl_usd": "+$12.00",
            "win_rate_pct": "66.7%",
            "order_rejections_1h": "1 (ord-rej-1: MIN_NOTIONAL on exchange)",
            "order_timeouts_1h": "1 (ord-to-2: TIMEOUT after 3200ms)",
            "order_fill_latency_p95_ms": "1450ms (baseline 180ms, window 2026-10-16 08:00-09:00 UTC)",
        }
    ]

    drift_detector = MagicMock(spec=BacktestDriftDetector)
    drift_detector.detect.side_effect = lambda sym: DriftReport(
        ticker_symbol=sym,
        simulated_fill_count=5,
        live_fill_count=4,
        simulated_quantity=Decimal("0.125"),
        live_quantity=Decimal("0.100"),
        simulated_average_price=Decimal("64395.00"),
        live_average_price=Decimal("64000.00"),
        fill_count_drift=1,
        quantity_drift=Decimal("0.025"),
        price_drift=Decimal("395.00"),
        drifted=True,
        window_start="2026-10-16T00:00:00Z",
        window_end="2026-10-16T06:00:00Z",
        partial_fill_legs_merged=1,
        simulated_fees=Decimal("3.20"),
        live_fees=Decimal("4.40"),
        fee_drift=Decimal("-1.20"),
    )

    backtest_report_text = (
        "=== Historical Backtest Report (BTC_USD) ===\n"
        f"Configuration Commit: {commit_v1}\n"
        "Period: 2026-09-01T00:00:00Z to 2026-10-01T00:00:00Z (UTC)\n"
        "Starting Capital: $10000.00 USD | Fee Assumption: 0.1% taker/maker | Slippage Model: 2 bps\n"
        "Total Return: +6.40% (+$640.00 Net Profit)\n"
        "Max Drawdown: -3.10%\n"
        "Total Trades: 28 (Win Rate: 64.3%, Profit Factor: 1.85)"
    )
    backtest_result_mock = MagicMock()
    backtest_result_mock.session_id = "bt-session-btc-01"
    backtest_result_mock.initial_balance = Decimal("10000")
    backtest_result_mock.fills = [MagicMock()] * 28
    backtest_result_mock.market_series = list(range(100))
    backtest_result_mock.report_markdown = backtest_report_text

    backtest_service = MagicMock()
    backtest_service.run.return_value = backtest_result_mock
    backtest_service.summary.return_value = BacktestSummary(
        session_id="bt-session-btc-01",
        ticker_symbol="BTC_USD",
        status="COMPLETED",
        return_pct=Decimal("6.40"),
        absolute_pnl=Decimal("640.00"),
        max_drawdown_pct=Decimal("-3.10"),
        round_trips=28,
        orders_filled=56,
        orders_cancelled=0,
        data_points=720,
        start_time=datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    backtest_tool = MagicMock(spec=BacktestTool)
    backtest_tool.name = "backtest"
    backtest_tool.backtest_service = backtest_service
    backtest_tool.invoke.return_value = backtest_report_text

    walk_forward_service = MagicMock(spec=WalkForwardApplicationService)
    walk_forward_service.list_runs.return_value = [
        {
            "run_id": "wf_cand_a",
            "candidate_id": "cand_exploratory_overfit",
            "ticker_symbol": "BTC_USD",
            "status": "COMPLETED",
            "performance_summary": {
                "candidate_name": "cand_exploratory_overfit",
                "stability_classification": "OVERFIT",
                "in_sample_return_pct": 18.40,
                "out_of_sample_return_pct": 1.20,
                "walk_forward_efficiency_ratio": 0.07,
                "max_out_of_sample_drawdown_pct": -8.90,
                "profitable_folds": 1,
                "total_folds": 4,
                "folds": [
                    {"fold_index": 1, "in_sample_return_pct": 5.0, "out_of_sample_return_pct": 6.2},
                    {"fold_index": 2, "in_sample_return_pct": 4.8, "out_of_sample_return_pct": -3.1},
                    {"fold_index": 3, "in_sample_return_pct": 4.2, "out_of_sample_return_pct": -1.4},
                    {"fold_index": 4, "in_sample_return_pct": 4.4, "out_of_sample_return_pct": -0.5},
                ],
            },
        },
        {
            "run_id": "wf_cand_b",
            "candidate_id": "cand_robust_multi",
            "ticker_symbol": "BTC_USD",
            "status": "COMPLETED",
            "performance_summary": {
                "candidate_name": "cand_robust_multi",
                "stability_classification": "ROBUST",
                "in_sample_return_pct": 9.20,
                "out_of_sample_return_pct": 6.80,
                "walk_forward_efficiency_ratio": 0.74,
                "max_out_of_sample_drawdown_pct": -2.40,
                "profitable_folds": 4,
                "total_folds": 4,
                "folds": [
                    {"fold_index": 1, "in_sample_return_pct": 2.3, "out_of_sample_return_pct": 1.8},
                    {"fold_index": 2, "in_sample_return_pct": 2.1, "out_of_sample_return_pct": 1.5},
                    {"fold_index": 3, "in_sample_return_pct": 2.4, "out_of_sample_return_pct": 1.9},
                    {"fold_index": 4, "in_sample_return_pct": 2.4, "out_of_sample_return_pct": 1.6},
                ],
            },
        },
    ]

    experiment_service = MagicMock()
    exp_901_record = {
        "experiment_id": "exp_901",
        "name": "BTC_USD Drift Recovery Study",
        "ticker_symbol": "BTC_USD",
        "status": "COMPLETED",
        "base_commit_hash": commit_v1,
        "branch_id": "branch_exp_901",
        "spec": {
            "triggered_by": {
                "trigger_type": "BACKTEST_DRIFT_DETECTED",
                "source_event_id": "evt_drift_77",
                "evidence_summary": (
                    "BTC_USD live average fill price drifted by +$395.00 (0.62% > 0.50% tolerance) "
                    "and fill count drifted (5 simulated vs 4 live) over 2026-10-16 00:00-06:00 UTC"
                ),
                "detected_at": "2026-10-16T06:05:00Z",
            }
        },
        "run_bindings": [
            {"candidate_id": "cand_current", "status": "COMPLETED", "backtest_session_id": "bt_901_cur", "walk_forward_run_id": "wf_cand_a"},
            {"candidate_id": "cand_equal_weight", "status": "COMPLETED", "backtest_session_id": "bt_901_eq", "walk_forward_run_id": "wf_cand_eq"},
            {"candidate_id": "cand_robust_multi", "status": "COMPLETED", "backtest_session_id": "bt_901_rob", "walk_forward_run_id": "wf_cand_b"},
        ],
        "report": {
            "recommended_candidate_id": "cand_robust_multi",
            "exploratory_winner_id": "cand_exploratory_overfit",
            "summary": "cand_robust_multi achieved +6.80% OOS return (WFE 0.74, 4/4 profitable folds).",
        },
    }
    experiment_service.get_experiment.return_value = exp_901_record
    experiment_service.list_experiments.return_value = [exp_901_record]

    retention_manager = MagicMock()
    retention_manager.status.return_value = {
        "enabled": True,
        "schedule": "DAILY",
        "dry_run": False,
        "grace_period": "7d",
    }
    retention_manager.list_policies.return_value = [
        {
            "policy_id": "pol_market_data",
            "data_category": "MARKET_DATA",
            "retention_period": "30d",
            "retention_mode": "DELETE",
            "enabled": True,
            "record_count": 15000,
        },
        {
            "policy_id": "pol_financial",
            "data_category": "FINANCIAL",
            "retention_period": "365d",
            "retention_mode": "KEEP",
            "enabled": True,
            "record_count": 420,
        },
    ]
    preview_run = RetentionRun(
        run_id="ret_preview_99",
        status=RetentionRunStatus.COMPLETED,
        trigger=RetentionTrigger.PREVIEW,
        dry_run=True,
        policy_version="v2",
        categories=[
            CategoryOutcome(
                data_category=DataCategory.MARKET_DATA,
                policy_id="pol_market_data",
                retention_mode=RetentionMode.DELETE,
                examined=15000,
                eligible=1200,
                deleted=0,
                skipped=2,
                skipped_reasons=[
                    SkipReason(reason="RETENTION_HOLD", count=1, detail="Active hold hold_audit_1 on order-88"),
                    SkipReason(reason="DEPENDENCY_REFERENCED", count=1, detail="Commit commit-a1 referenced by active order"),
                ],
            )
        ],
    ).to_dict()
    completed_run = RetentionRun(
        run_id="ret_run_01",
        status=RetentionRunStatus.COMPLETED,
        trigger=RetentionTrigger.SCHEDULED,
        dry_run=False,
        policy_version="v2",
        categories=[
            CategoryOutcome(
                data_category=DataCategory.MARKET_DATA,
                policy_id="pol_market_data",
                retention_mode=RetentionMode.DELETE,
                examined=14600,
                eligible=802,
                deleted=800,
                skipped=2,
                skipped_reasons=[
                    SkipReason(reason="RETENTION_HOLD", count=1, detail="Active hold hold_audit_1 on order-88"),
                    SkipReason(reason="DEPENDENCY_REFERENCED", count=1, detail="Commit commit-a1 referenced by active order"),
                ],
            )
        ],
    ).to_dict()
    retention_manager.preview.return_value = preview_run
    retention_manager.list_runs.return_value = [completed_run]
    retention_manager.get_run.return_value = completed_run

    account_manager = MagicMock(spec=AccountManager)
    account_manager.get_base_balance.return_value = AccountBalance(currency="BTC", available_balance=Decimal("0.125"))
    account_manager.get_quote_balance.return_value = AccountBalance(currency="USD", available_balance=Decimal("4400"))

    tools: dict[str, Any] = {
        "trading_health": TradingHealthTool(health_monitor=health_monitor),
        "exchange_read_api": ExchangeReadOnlyTool(rest_manager=rest_manager),
        "portfolio_summary": PortfolioSummaryTool(portfolio_risk_manager=portfolio_risk_manager),
        "get_open_orders": GetOpenOrdersTool(order_manager=order_manager, assets=assets),
        "account_balance": AccountBalanceTool(account_manager=account_manager, assets=assets),
        "inspect_trading_decision": DecisionInspectorTool(decision_manager=decision_manager),
        "get_configuration": ConfigurationTool(configuration_service=config_service),
        "get_configuration_history": ConfigurationHistoryTool(vcs=vcs),
        "query_metrics": MetricsTool(metric_service=metric_service),
        "get_trade_attribution": TradeAttributionTool(database_manager=mock_order_db),
        "detect_backtest_drift": BacktestDriftTool(drift_detector=drift_detector),
        "backtest": backtest_tool,
        "walk_forward": WalkForwardTool(walk_forward_service=walk_forward_service),
        "inspect_schedule_tick_trace": TickTraceTool(
            tick_tracer=tick_tracer,
            activity_tracker=activity_tracker,
            decision_manager=decision_manager,
        ),
        "inspect_experiment": ExperimentInspectorTool(
            experiment_service=experiment_service,
            health_monitor=health_monitor,
            activity_tracker=activity_tracker,
            drift_detector=drift_detector,
        ),
        "inspect_retention_governance": RetentionGovernanceTool(
            retention_manager=retention_manager,
        ),
    }

    return SeededBenchmarkEnvironment(
        db_manager=db,
        vcs=vcs,
        commit_v1=commit_v1,
        commit_v2=commit_v2,
        decision_manager=decision_manager,
        portfolio_risk_manager=portfolio_risk_manager,
        health_monitor=health_monitor,
        activity_tracker=activity_tracker,
        tick_tracer=tick_tracer,
        tools=tools,
        timeline_projector=timeline_projector,
        approval_service=approval_service,
    )
