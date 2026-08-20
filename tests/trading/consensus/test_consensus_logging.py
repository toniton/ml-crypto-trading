import logging
from decimal import Decimal
from unittest import TestCase

import pytest

from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.trading.consensus.consensus_factor import ConsensusFactor
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.strategies.expression_strategy import ExpressionStrategy


def _context():
    return TradingContext(ticker_symbol="BTC_USD", exchange="BACKTEST", starting_balance=Decimal("1000"))


def _market(close="150"):
    return MarketData(
        volume=Decimal("1000"),
        high_price=Decimal("155"),
        low_price=Decimal("145"),
        close_price=Decimal(close),
        timestamp=0,
    )


def _strategy(name, expression="close > 100", action=TradeAction.BUY, ticker_symbols=None):
    return ExpressionStrategy(
        StrategyConfig(
            name=name,
            type=StrategyType.DYNAMIC,
            action=action,
            expression=expression,
        ),
        ticker_symbols=ticker_symbols,
    )


def _consensus_lines(manager, call):
    logger_name = manager.app_logger.name
    with TestCase().assertLogs(logger_name, level=logging.INFO) as captured:
        result = call()
    return result, captured.output


def test_consensus_logs_strategy_names_and_votes():
    manager = ConsensusManager(ConsensusFactor(buy=1.3, sell=0.5))
    manager.register_strategy(_strategy("RsiBuy"))
    manager.register_strategy(_strategy("MomentumBuy", expression="close < 100"))

    result, lines = _consensus_lines(
        manager,
        lambda: manager.get_quorum(TradeAction.BUY, "BTC_USD", _context(), _market(), []),
    )

    assert result is False
    assert "Consensus [BTC_USD BUY]: RsiBuy=True, MomentumBuy=False -> Quorum=False (1/2)" in lines[-1]


def test_consensus_logs_quorum_reached():
    manager = ConsensusManager(ConsensusFactor(buy=0.5, sell=0.5))
    manager.register_strategy(_strategy("RsiBuy"))

    result, lines = _consensus_lines(
        manager,
        lambda: manager.get_quorum(TradeAction.BUY, "BTC_USD", _context(), _market(), []),
    )

    assert result is True
    assert "Consensus [BTC_USD BUY]: RsiBuy=True -> Quorum=True (1/1)" in lines[-1]


def test_consensus_logs_absent_bucket():
    manager = ConsensusManager(ConsensusFactor(buy=1.3, sell=0.5))

    result, lines = _consensus_lines(
        manager,
        lambda: manager.get_quorum(TradeAction.BUY, "BTC_USD", _context(), _market(), []),
    )

    assert result is False
    assert "Consensus [BTC_USD BUY]: no strategies registered -> Quorum=False" in lines[-1]


def test_strategy_only_votes_for_its_ticker_symbols():
    manager = ConsensusManager(ConsensusFactor(buy=1.3, sell=0.5))
    manager.register_strategy(_strategy("RsiBuy", ticker_symbols={"BTC_USD"}))

    assert manager.get_quorum(TradeAction.BUY, "BTC_USD", _context(), _market(), []) is True
    assert manager.get_quorum(TradeAction.BUY, "DOGE_USD", _context(), _market(), []) is False


def test_unrestricted_strategy_votes_for_any_ticker():
    manager = ConsensusManager(ConsensusFactor(buy=1.3, sell=0.5))
    manager.register_strategy(_strategy("RsiBuy"))

    assert manager.get_quorum(TradeAction.BUY, "BTC_USD", _context(), _market(), []) is True
    assert manager.get_quorum(TradeAction.BUY, "DOGE_USD", _context(), _market(), []) is True


def test_register_strategy_with_empty_ticker_symbols_fails_fast():
    from src.trading.strategies.expression_strategy import ExpressionStrategy

    manager = ConsensusManager(ConsensusFactor(buy=1.3, sell=0.5))
    strategy = ExpressionStrategy(
        StrategyConfig(
            name="Broken",
            type=StrategyType.DYNAMIC,
            action=TradeAction.BUY,
            expression="close > 100",
        ),
        ticker_symbols=set(),
    )

    with pytest.raises(ValueError, match="not bound to any ticker"):
        manager.register_strategy(strategy)