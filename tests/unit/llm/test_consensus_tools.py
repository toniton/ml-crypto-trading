import unittest
from unittest.mock import MagicMock

from api.interfaces.trade_action import TradeAction
from src.llm.tools.consensus_tool import ConsensusTool
from src.llm.tools.strategy_votes_tool import StrategyVotesTool
from src.trading.consensus.consensus_decision import ConsensusDecision
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.markets.market_data_manager import MarketDataManager
from src.trading.session.session_manager import SessionManager


def _asset():
    asset = MagicMock()
    asset.ticker_symbol = "BTC_USD"
    asset.key = 123
    return asset


def _decision():
    return ConsensusDecision(
        trade_action=TradeAction.BUY,
        ticker_symbol="BTC_USD",
        votes={"Hammer": True, "Rsi": False},
        weights={"Hammer": 1.0, "Rsi": 1.0},
        factor=1.3,
    )


def _build_managers():
    consensus_manager = MagicMock(spec=ConsensusManager)
    consensus_manager.evaluate.return_value = _decision()

    session = MagicMock()
    session.trading_contexts = {123: MagicMock()}
    session_manager = MagicMock(spec=SessionManager)
    session_manager.current_session = session

    market_data_manager = MagicMock(spec=MarketDataManager)
    market_data_manager.get_market_data.return_value = MagicMock()
    market_data_manager.get_candles.return_value = []

    return consensus_manager, session_manager, market_data_manager


class TestConsensusTool(unittest.TestCase):
    def test_formats_full_decision(self):
        consensus_manager, session_manager, market_data_manager = _build_managers()
        tool = ConsensusTool(
            consensus_manager=consensus_manager,
            session_manager=session_manager,
            market_data_manager=market_data_manager,
            assets=[_asset()],
        )
        result = tool._run("BTC_USD", "BUY")
        self.assertIn("Consensus [BTC_USD BUY]", result)
        self.assertIn("Hammer=True", result)
        self.assertIn("Quorum:", result)
        self.assertIn("Vote ratio:", result)
        consensus_manager.evaluate.assert_called_once()

    def test_asset_not_found(self):
        consensus_manager, session_manager, market_data_manager = _build_managers()
        tool = ConsensusTool(
            consensus_manager=consensus_manager,
            session_manager=session_manager,
            market_data_manager=market_data_manager,
            assets=[],
        )
        self.assertIn("not found", tool._run("ETH_USD", "BUY"))

    def test_invalid_action(self):
        consensus_manager, session_manager, market_data_manager = _build_managers()
        tool = ConsensusTool(
            consensus_manager=consensus_manager,
            session_manager=session_manager,
            market_data_manager=market_data_manager,
            assets=[_asset()],
        )
        self.assertIn("must be 'BUY' or 'SELL'", tool._run("BTC_USD", "HOLD"))

    def test_no_active_session(self):
        consensus_manager, session_manager, market_data_manager = _build_managers()
        session_manager.current_session = None
        tool = ConsensusTool(
            consensus_manager=consensus_manager,
            session_manager=session_manager,
            market_data_manager=market_data_manager,
            assets=[_asset()],
        )
        self.assertIn("No active trading session", tool._run("BTC_USD", "BUY"))


class TestStrategyVotesTool(unittest.TestCase):
    def test_formats_votes_only(self):
        consensus_manager, session_manager, market_data_manager = _build_managers()
        tool = StrategyVotesTool(
            consensus_manager=consensus_manager,
            session_manager=session_manager,
            market_data_manager=market_data_manager,
            assets=[_asset()],
        )
        result = tool._run("BTC_USD", "BUY")
        self.assertIn("Strategy votes [BTC_USD BUY]", result)
        self.assertIn("Hammer=True", result)
        self.assertNotIn("Quorum:", result)
