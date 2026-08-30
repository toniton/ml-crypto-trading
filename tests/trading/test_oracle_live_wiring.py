from __future__ import annotations

from decimal import Decimal
from queue import Queue
from unittest.mock import MagicMock

from api.interfaces.account_balance import AccountBalance
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.agent.oracle.events import ORACLE_SUMMARY_EVENT_TYPE, OracleSummaryEvent
from src.agent.oracle.oracle_service import OracleService
from src.events.message_event_bus import CallbackSubscription, MessageEventBus
from src.trading.consensus.consensus_decision import ConsensusDecision
from src.trading.managers.manager_container import ManagerContainer
from src.trading.trading_executor import TradingExecutor


def _asset() -> MagicMock:
    asset = MagicMock()
    asset.min_quantity = 0.001
    asset.quantity_decimals = 3
    asset.quote_decimals = 2
    asset.exchange.value = "test_exchange"
    asset.ticker_symbol = "BTC_USD"
    asset.quote_ticker_symbol = "USD"
    asset.key = 1
    return asset


def _manager_container() -> MagicMock:
    manager_container = MagicMock(spec=ManagerContainer)
    manager_container.account_manager = MagicMock()
    manager_container.market_data_manager = MagicMock()
    manager_container.session_manager = MagicMock()
    manager_container.consensus_manager = MagicMock()
    manager_container.fees_manager = MagicMock()
    manager_container.order_manager = MagicMock()
    manager_container.protection_manager = MagicMock()
    manager_container.websocket_manager = MagicMock()
    return manager_container


def _stub_buy_sources(manager_container: MagicMock) -> None:
    manager_container.account_manager.get_quote_balance.return_value = AccountBalance(
        "USD", Decimal("1000")
    )
    manager_container.market_data_manager.get_market_data.return_value = MarketData(
        volume=Decimal("100"),
        high_price=Decimal("110"),
        low_price=Decimal("90"),
        close_price=Decimal("100"),
        timestamp=123456789.0,
    )
    manager_container.fees_manager.get_instrument_fees.return_value = Fees(
        Decimal("0.1"), Decimal("0.1")
    )
    manager_container.market_data_manager.get_candles.return_value = []
    manager_container.session_manager.get_trading_context.return_value = TradingContext(
        "BTC_USD", "test_exchange", Decimal("1000")
    )
    manager_container.protection_manager.can_trade.return_value = True
    manager_container.consensus_manager.evaluate.return_value = ConsensusDecision(
        TradeAction.BUY, "BTC_USD", {"s0": True}, {"s0": 1.0}, 1.3
    )
    buy_order = MagicMock()
    buy_order.uuid = "order-1"
    buy_order.model_dump_json.return_value = "{}"
    manager_container.order_manager.open_order.return_value = buy_order


def test_executor_events_flow_to_oracle_and_publish_summary():
    asset = _asset()
    manager_container = _manager_container()
    event_bus = MessageEventBus()

    executor = TradingExecutor([], manager_container, Queue(), event_bus=event_bus)

    llm = MagicMock()
    llm.generate.return_value = "live summary"
    oracle = OracleService(llm, publish_bus=event_bus)
    oracle.subscribe(event_bus)

    collected = []
    event_bus.subscribe(ORACLE_SUMMARY_EVENT_TYPE, CallbackSubscription(collected.append))

    _stub_buy_sources(manager_container)
    executor.create_buy_order([asset])

    assert llm.generate.call_count == 1
    assert oracle.get_latest_summary() is not None
    assert oracle.get_latest_summary().market_state == "active"
    assert oracle.get_latest_summary().summary == "live summary"
    assert len(collected) == 1
    assert isinstance(collected[0], OracleSummaryEvent)
