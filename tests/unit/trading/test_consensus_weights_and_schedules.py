from datetime import datetime, time, timezone
from decimal import Decimal
import pytest

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.consensus.consensus_factor import ConsensusFactor
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.strategies.expression_strategy import ExpressionStrategy
from src.trading.strategies.models.strategy_schedule import (
    StrategySchedule,
    TradingWindow,
    Weekday,
)


def _asset(ticker="BTC_USD", buy=0.5, sell=0.5) -> Asset:
    base, quote = ticker.split("_") if "_" in ticker else (ticker, "USD")
    return Asset(
        base_ticker_symbol=base,
        quote_ticker_symbol=quote,
        quote_decimals=2,
        name=ticker,
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.001,
        quantity_decimals=3,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=Timeframe.MIN1,
        consensus=ConsensusFactor(buy=buy, sell=sell),
    )


def _context() -> TradingContext:
    return TradingContext(ticker_symbol="BTC_USD", exchange="BACKTEST", starting_balance=Decimal("1000"))


def _market(timestamp_epoch: float) -> MarketData:
    return MarketData(
        volume=Decimal("1000"),
        high_price=Decimal("155"),
        low_price=Decimal("145"),
        close_price=Decimal("150"),
        timestamp=timestamp_epoch,
    )


class TestConsensusWeightsAndSchedules:
    def test_single_strategy_in_window_reaches_quorum(self):
        # Monday 10:00 UTC (12:00 Stockholm)
        epoch = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc).timestamp()

        schedule = StrategySchedule(
            timezone="UTC",
            windows=[
                TradingWindow(
                    days=[Weekday.MONDAY],
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                )
            ],
        )

        strategy = ExpressionStrategy(
            StrategyConfig(
                name="Trend",
                type=StrategyType.DYNAMIC,
                action=TradeAction.BUY,
                expression="close > 100",
                weight=1.0,
                schedule=schedule,
            )
        )

        manager = ConsensusManager()
        manager.set_factors([_asset("BTC_USD", buy=0.5)])
        manager.register_strategy(strategy)

        decision = manager.evaluate(TradeAction.BUY, "BTC_USD", _context(), _market(epoch), [])
        assert decision.quorum is True
        assert decision.votes["Trend"] is True
        assert decision.weights["Trend"] == 1.0

    def test_single_strategy_outside_window_fails_quorum(self):
        # Tuesday 10:00 UTC (window only Monday)
        epoch = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc).timestamp()

        schedule = StrategySchedule(
            timezone="UTC",
            windows=[
                TradingWindow(
                    days=[Weekday.MONDAY],
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                )
            ],
        )

        strategy = ExpressionStrategy(
            StrategyConfig(
                name="Trend",
                type=StrategyType.DYNAMIC,
                action=TradeAction.BUY,
                expression="close > 100",
                weight=1.0,
                schedule=schedule,
            )
        )

        manager = ConsensusManager()
        manager.set_factors([_asset("BTC_USD", buy=0.5)])
        manager.register_strategy(strategy)

        decision = manager.evaluate(TradeAction.BUY, "BTC_USD", _context(), _market(epoch), [])
        assert decision.quorum is False
        assert decision.votes["Trend"] is False
        assert decision.weights["Trend"] == 0.0

    def test_two_strategies_one_active_one_inactive_does_not_penalize_active(self):
        # Monday 10:00 UTC
        epoch = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc).timestamp()

        # Strategy 1 active on Mondays
        strat1 = ExpressionStrategy(
            StrategyConfig(
                name="MonStrategy",
                type=StrategyType.DYNAMIC,
                action=TradeAction.BUY,
                expression="close > 100",
                weight=1.0,
                schedule=StrategySchedule(
                    timezone="UTC",
                    windows=[TradingWindow(days=[Weekday.MONDAY], start_time=time(9, 0), end_time=time(17, 0))],
                ),
            )
        )
        # Strategy 2 active only on Tuesdays
        strat2 = ExpressionStrategy(
            StrategyConfig(
                name="TueStrategy",
                type=StrategyType.DYNAMIC,
                action=TradeAction.BUY,
                expression="close > 100",
                weight=1.0,
                schedule=StrategySchedule(
                    timezone="UTC",
                    windows=[TradingWindow(days=[Weekday.TUESDAY], start_time=time(9, 0), end_time=time(17, 0))],
                ),
            )
        )

        manager = ConsensusManager()
        manager.set_factors([_asset("BTC_USD", buy=0.5)])
        manager.register_strategy(strat1)
        manager.register_strategy(strat2)

        decision = manager.evaluate(TradeAction.BUY, "BTC_USD", _context(), _market(epoch), [])
        assert decision.votes["MonStrategy"] is True
        assert decision.weights["MonStrategy"] == 1.0
        assert decision.votes["TueStrategy"] is False
        assert decision.weights["TueStrategy"] == 0.0
        assert decision.quorum is True
        assert decision.weighted_true_count == 1.0
        assert decision.weighted_false_count == 0.0

    def test_weighted_consensus_with_different_weights(self):
        epoch = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc).timestamp()

        # Strategy A (weight 0.8, votes True)
        strat_a = ExpressionStrategy(
            StrategyConfig(
                name="HeavyStrategy",
                type=StrategyType.DYNAMIC,
                action=TradeAction.BUY,
                expression="close > 100",
                weight=0.8,
            )
        )
        # Strategy B (weight 0.2, votes False)
        strat_b = ExpressionStrategy(
            StrategyConfig(
                name="LightStrategy",
                type=StrategyType.DYNAMIC,
                action=TradeAction.BUY,
                expression="close < 50",  # False since close is 150
                weight=0.2,
            )
        )

        manager = ConsensusManager()
        # factor = 1.0 means margin = true_weight - 1.0 * false_weight
        # margin = 0.8 - 1.0 * 0.2 = 0.6 >= 0 -> quorum met!
        manager.set_factors([_asset("BTC_USD", buy=1.0)])
        manager.register_strategy(strat_a)
        manager.register_strategy(strat_b)

        decision = manager.evaluate(TradeAction.BUY, "BTC_USD", _context(), _market(epoch), [])
        assert decision.quorum is True
        assert decision.weighted_vote_ratio == pytest.approx(0.8 / 1.0)
        assert decision.quorum_margin == pytest.approx(0.6)
