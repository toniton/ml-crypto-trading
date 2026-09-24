from __future__ import annotations

from decimal import Decimal

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.events.message_event_bus import CallbackSubscription, MessageEventBus
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.consensus.consensus_factor import ConsensusFactor
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.events import ConsensusEvaluatedEvent
from src.trading.strategies.expression_strategy import ExpressionStrategy


def _asset(base="BTC", quote="USD", buy=0.5, sell=0.5) -> Asset:
    return Asset(
        base_ticker_symbol=base,
        quote_ticker_symbol=quote,
        quote_decimals=2,
        name=f"{base}-{quote}",
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.001,
        quantity_decimals=3,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=Timeframe.MIN1,
        consensus=ConsensusFactor(buy=buy, sell=sell),
    )


def _strategy(name: str, expression: str = "close > 100", action: TradeAction = TradeAction.BUY) -> ExpressionStrategy:
    return ExpressionStrategy(
        StrategyConfig(
            name=name,
            type=StrategyType.DYNAMIC,
            action=action,
            expression=expression,
        )
    )


def test_consensus_manager_publishes_event_on_evaluate():
    bus = MessageEventBus()
    events: list[ConsensusEvaluatedEvent] = []
    bus.subscribe(ConsensusEvaluatedEvent.__name__, CallbackSubscription(events.append))

    manager = ConsensusManager(event_bus=bus)
    manager.set_factors([_asset("BTC", "USD", buy=0.5, sell=0.5)])
    manager.register_strategy(_strategy("RsiBuy", expression="close > 100"))

    context = TradingContext(ticker_symbol="BTC_USD", exchange="BACKTEST", starting_balance=Decimal("1000"))
    market_data = MarketData(
        volume=Decimal("1000"),
        high_price=Decimal("155"),
        low_price=Decimal("145"),
        close_price=Decimal("150"),
        timestamp=1234567.0,
    )

    decision = manager.evaluate(TradeAction.BUY, "BTC_USD", context, market_data, [])

    assert decision.quorum is True
    assert len(events) == 1
    ev = events[0]
    assert ev.symbol == "BTC_USD"
    assert ev.decision == "BUY"
    assert ev.quorum_met is True
    assert ev.buy_votes == 1
    assert ev.sell_votes == 0
    assert ev.total_strategies == 1
    assert ev.evaluated_at == 1234567.0
    assert ev.factors["factor"] == 0.5
    assert ev.asset == "BTC_USD"
    assert ev.actor_type == "SYSTEM"
    assert ev.source == "consensus_manager"
