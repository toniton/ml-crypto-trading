from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.consensus.consensus_factor import ConsensusFactor
from src.backtest.backtest_clock import BacktestClock
from src.backtest.backtest_data_loader import HistoricalDataPoint
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.backtest_simulator import BacktestSimulator
from src.backtest.data.backtest_data_set import BacktestDataSet
from src.backtest.execution.backtest_execution_engine import BacktestExecutionEngine
from src.backtest.execution.execution_model import ExecutionModel
from src.backtest.execution.latency.fixed_latency import FixedLatencyModel
from src.backtest.execution.slippage.fixed_tick_slippage import FixedTickSlippage
from src.backtest.execution.fees.percentage_fee import PercentageFee
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.core.weekday import Weekday
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.strategies.expression_strategy import ExpressionStrategy
from src.trading.strategies.models.strategy_schedule import StrategySchedule, TradingWindow
from src.trading.strategies.strategy_weight_resolver import StrategyWeightResolver


def test_backtest_clock_drives_strategy_schedule_resolution():
    # Strategy active Mon-Fri 09:00 - 16:00 Stockholm time (UTC+2 in summer, UTC+1 in winter)
    schedule = StrategySchedule(
        timezone="Europe/Stockholm",
        windows=[
            TradingWindow(
                days=[
                    Weekday.MONDAY,
                    Weekday.TUESDAY,
                    Weekday.WEDNESDAY,
                    Weekday.THURSDAY,
                    Weekday.FRIDAY,
                ],
                start_time="09:00:00",
                end_time="16:00:00",
            )
        ],
    )

    strategy_config = StrategyConfig(
        name="TrendFollower",
        type=StrategyType.DYNAMIC,
        action=TradeAction.BUY,
        expression="close > 0",
        enabled=True,
        weight=1.5,
        schedule=schedule,
    )
    strategy = ExpressionStrategy(config=strategy_config)

    # 1. Backtest tick at Wednesday 10:00 UTC (12:00 Stockholm in summer) -> Active
    summer_wed_active_utc = datetime(2026, 6, 10, 10, 0, 0, tzinfo=timezone.utc).timestamp()
    effective_weight = StrategyWeightResolver.resolve_effective_weight(strategy, summer_wed_active_utc)
    assert effective_weight == 1.5

    # 2. Backtest tick at Wednesday 18:00 UTC (20:00 Stockholm) -> Inactive
    summer_wed_inactive_utc = datetime(2026, 6, 10, 18, 0, 0, tzinfo=timezone.utc).timestamp()
    effective_weight = StrategyWeightResolver.resolve_effective_weight(strategy, summer_wed_inactive_utc)
    assert effective_weight == 0.0

    # 3. Backtest tick on Saturday -> Inactive
    weekend_utc = datetime(2026, 6, 13, 11, 0, 0, tzinfo=timezone.utc).timestamp()
    effective_weight = StrategyWeightResolver.resolve_effective_weight(strategy, weekend_utc)
    assert effective_weight == 0.0


def test_backtest_simulator_consensus_evaluation_with_schedule():
    # 2 timestamps: 10:00 UTC (12:00 local, active) and 18:00 UTC (20:00 local, inactive)
    t1 = int(datetime(2026, 6, 10, 10, 0, 0, tzinfo=timezone.utc).timestamp())
    t2 = int(datetime(2026, 6, 10, 18, 0, 0, tzinfo=timezone.utc).timestamp())

    asset = Asset(
        base_ticker_symbol="TEST",
        quote_ticker_symbol="USD",
        name="TEST_USD",
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.01,
        quantity_decimals=2,
        quote_decimals=2,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=Timeframe.MIN1,
        consensus=ConsensusFactor(buy=1.0, sell=1.0),
    )

    dp1 = HistoricalDataPoint(
        timestamp=t1,
        open_price=Decimal("100"),
        high_price=Decimal("105"),
        low_price=Decimal("95"),
        close_price=Decimal("102"),
        volume=Decimal("1000"),
        market_cap=Decimal("1000000"),
    )
    dp2 = HistoricalDataPoint(
        timestamp=t2,
        open_price=Decimal("102"),
        high_price=Decimal("108"),
        low_price=Decimal("101"),
        close_price=Decimal("107"),
        volume=Decimal("1200"),
        market_cap=Decimal("1000000"),
    )

    dataset = BacktestDataSet(
        dataset_id="ds-1",
        ticker_symbol="TEST_USD",
        start_time=datetime.fromtimestamp(t1, tz=timezone.utc),
        end_time=datetime.fromtimestamp(t2, tz=timezone.utc),
        data_points=(dp1, dp2),
    )
    datasets = {"TEST_USD": dataset}
    clock = BacktestClock(timestamps={"TEST_USD": [t1, t2]})
    bus = BacktestEventBus()
    model = ExecutionModel(
        latency=FixedLatencyModel(0.0),
        slippage=FixedTickSlippage(0),
        fees=PercentageFee(Decimal("0")),
    )
    engine = BacktestExecutionEngine(
        clock=clock,
        datasets=datasets,
        bus=bus,
        execution_model=model,
        assets={"TEST_USD": asset},
        initial_balance=Decimal("10000.0"),
    )

    schedule = StrategySchedule(
        timezone="Europe/Stockholm",
        windows=[
            TradingWindow(
                days=[Weekday.WEDNESDAY],
                start_time="09:00:00",
                end_time="16:00:00",
            )
        ],
    )
    strat_config = StrategyConfig(
        name="Strat1",
        type=StrategyType.DYNAMIC,
        action=TradeAction.BUY,
        expression="close > 0",
        weight=2.0,
        schedule=schedule,
        enabled=True,
    )
    strat = ExpressionStrategy(config=strat_config)

    consensus_mgr = ConsensusManager()
    consensus_mgr.set_factors([asset])
    consensus_mgr.register_strategy(strat)
    eval_weights: list[float] = []

    context = TradingContext(
        ticker_symbol="TEST_USD",
        exchange="BACKTEST",
        starting_balance=Decimal("1000"),
    )

    def on_tick(cur_asset, _timestamp, market_data, candles):
        if market_data:
            decision = consensus_mgr.evaluate(
                TradeAction.BUY,
                cur_asset.ticker_symbol,
                context,
                market_data,
                candles,
            )
            weight = decision.weights["Strat1"] if "Strat1" in decision.weights else 0.0
            eval_weights.append(weight)

    sim = BacktestSimulator(
        clock=clock,
        datasets=datasets,
        execution_engine=engine,
        bus=bus,
        strategy=on_tick,
    )

    sim.run([asset])

    assert len(eval_weights) == 2
    assert eval_weights[0] == 2.0
    assert eval_weights[1] == 0.0
