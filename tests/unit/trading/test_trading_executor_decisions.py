from decimal import Decimal
from queue import Queue
from unittest.mock import MagicMock

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from api.interfaces.trading_context import PositionEntry, TradingContext
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.core.interfaces.event_bus import EventBus
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.consensus.consensus_decision import ConsensusDecision
from src.trading.decision.trading_decision import DecisionStatus, TradingDecision
from src.trading.events.domain_events import TradingDecisionCreatedEvent
from src.trading.managers.manager_container import ManagerContainer
from src.trading.sizing.position_sizer import PositionSizer
from src.trading.strategies.strategy_registry import StrategyRegistry
from src.trading.trading_executor import TradingExecutor


def _create_test_asset() -> Asset:
    return Asset(
        base_ticker_symbol="BTC",
        quote_ticker_symbol="USD",
        quote_decimals=2,
        name="Bitcoin",
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.001,
        quantity_decimals=3,
        schedule=1,
        candles_timeframe="MIN1",
        enabled=True,
        strategies=[
            StrategyConfig(
                name="BuyLowerThanLowestBuyStrategy",
                type=StrategyType.STATIC,
                action=TradeAction.BUY,
                class_name="BuyLowerThanLowestBuyStrategy",
                enabled=True,
            )
        ],
    )


def test_trading_executor_records_decision_on_successful_buy():
    asset = _create_test_asset()
    event_bus = MagicMock(spec=EventBus)
    decision_repo = MagicMock()
    
    account_mgr = MagicMock()
    account_mgr.get_quote_balance.return_value = AccountBalance(
        currency="USD", available_balance=Decimal("10000")
    )
    market_mgr = MagicMock()
    market_mgr.get_market_data.return_value = MarketData(
        close_price=Decimal("50000"),
        high_price=Decimal("51000"),
        low_price=Decimal("49000"),
        volume=Decimal("100"),
        timestamp=1700000000.0,
        bid_price=Decimal("49990"),
        ask_price=Decimal("50010"),
    )
    market_mgr.get_candles.return_value = []
    fees_mgr = MagicMock()
    fees_mgr.get_instrument_fees.return_value = Fees(
        maker_fee_pct=Decimal("0.001"), taker_fee_pct=Decimal("0.002")
    )
    consensus_mgr = MagicMock()
    consensus_mgr.evaluate.return_value = ConsensusDecision(
        trade_action=TradeAction.BUY,
        ticker_symbol="BTC",
        votes={"BuyLowerThanLowestBuyStrategy": True},
        weights={"BuyLowerThanLowestBuyStrategy": 1.0},
        factor=1.0,
    )

    created_order = Order(
        uuid="order-xyz-123",
        provider_name="BACKTEST",
        ticker_symbol="BTC_USD",
        price=Decimal("50000"),
        quantity="0.1",
        trade_action=TradeAction.BUY,
        created_time=1700000000.0,
        status=OrderStatus.PENDING,
    )
    order_mgr = MagicMock()
    order_mgr.has_outstanding_intent.return_value = False
    order_mgr.open_order.return_value = created_order

    portfolio_risk_mgr = MagicMock()
    portfolio_risk_mgr.can_trade.return_value = (True, None)
    
    session_mgr = MagicMock()
    session_mgr.get_current_commit_hash.return_value = "commit-abc-123"

    container = ManagerContainer(
        account_manager=account_mgr,
        fees_manager=fees_mgr,
        order_manager=order_mgr,
        market_data_manager=market_mgr,
        consensus_manager=consensus_mgr,
        protection_manager=MagicMock(),
        session_manager=session_mgr,
        websocket_manager=MagicMock(),
        rest_manager=MagicMock(),
        portfolio_risk_manager=portfolio_risk_mgr,
        reconciliation_engine=MagicMock(),
        health_monitor=None,
    )

    executor = TradingExecutor(
        assets=[asset],
        manager_container=container,
        activity_queue=Queue(),
        position_sizer=PositionSizer(),
        strategies_registry=StrategyRegistry(),
        event_bus=event_bus,
        decision_repository=decision_repo,
    )

    executor._process_buy_asset(asset)

    # Verify decision was saved
    assert decision_repo.save.call_count >= 1
    saved_decision: TradingDecision = decision_repo.save.call_args[0][0]
    
    assert saved_decision.trade_action == TradeAction.BUY
    assert saved_decision.status == DecisionStatus.EXECUTED
    assert saved_decision.ticker_symbol == "BTC_USD"
    assert saved_decision.commit_hash == "commit-abc-123"
    assert saved_decision.resulting_order_id == "order-xyz-123"
    assert saved_decision.market_snapshot.close_price == Decimal("50000")
    assert saved_decision.market_snapshot.ask_price == Decimal("50010")
    assert saved_decision.consensus_snapshot.quorum is True
    assert saved_decision.risk_evaluation.passed is True
    
    # Verify open_order received decision_id
    order_call_kwargs = order_mgr.open_order.call_args[1]
    assert order_call_kwargs.get("decision_id") == saved_decision.decision_id
    
    # Verify TradingDecisionCreatedEvent was published
    assert event_bus.publish.called
    events = [call[0][0] for call in event_bus.publish.call_args_list if isinstance(call[0][0], TradingDecisionCreatedEvent)]
    assert len(events) >= 1
    assert events[0].decision.decision_id == saved_decision.decision_id


def test_trading_executor_records_decision_when_risk_rejects():
    asset = _create_test_asset()
    event_bus = MagicMock(spec=EventBus)
    decision_repo = MagicMock()
    
    account_mgr = MagicMock()
    account_mgr.get_quote_balance.return_value = AccountBalance(
        currency="USD", available_balance=Decimal("10000")
    )
    market_mgr = MagicMock()
    market_mgr.get_market_data.return_value = MarketData(
        close_price=Decimal("50000"),
        high_price=Decimal("51000"),
        low_price=Decimal("49000"),
        volume=Decimal("100"),
        timestamp=1700000000.0,
    )
    market_mgr.get_candles.return_value = []
    fees_mgr = MagicMock()
    fees_mgr.get_instrument_fees.return_value = Fees(
        maker_fee_pct=Decimal("0.001"), taker_fee_pct=Decimal("0.002")
    )
    consensus_mgr = MagicMock()
    consensus_mgr.evaluate.return_value = ConsensusDecision(
        trade_action=TradeAction.BUY,
        ticker_symbol="BTC",
        votes={"BuyLowerThanLowestBuyStrategy": True},
        weights={"BuyLowerThanLowestBuyStrategy": 1.0},
        factor=1.0,
    )

    order_mgr = MagicMock()
    order_mgr.has_outstanding_intent.return_value = False

    portfolio_risk_mgr = MagicMock()
    portfolio_risk_mgr.can_trade.return_value = (False, "Max asset exposure exceeded")

    container = ManagerContainer(
        account_manager=account_mgr,
        fees_manager=fees_mgr,
        order_manager=order_mgr,
        market_data_manager=market_mgr,
        consensus_manager=consensus_mgr,
        protection_manager=MagicMock(),
        session_manager=MagicMock(),
        websocket_manager=MagicMock(),
        rest_manager=MagicMock(),
        portfolio_risk_manager=portfolio_risk_mgr,
        reconciliation_engine=MagicMock(),
        health_monitor=None,
    )

    executor = TradingExecutor(
        assets=[asset],
        manager_container=container,
        activity_queue=Queue(),
        position_sizer=PositionSizer(),
        strategies_registry=StrategyRegistry(),
        event_bus=event_bus,
        decision_repository=decision_repo,
    )

    executor._process_buy_asset(asset)

    # Verify decision was saved as REJECTED
    assert decision_repo.save.call_count >= 1
    saved_decision: TradingDecision = decision_repo.save.call_args[0][0]
    assert saved_decision.status == DecisionStatus.REJECTED
    assert saved_decision.rejection_reason == "RISK_REJECTED"
    assert saved_decision.risk_evaluation.rejection_reason == "Max asset exposure exceeded"
    assert saved_decision.resulting_order_id is None
    # No order opened
    order_mgr.open_order.assert_not_called()


def test_trading_executor_records_decision_on_successful_sell():
    asset = Asset(
        base_ticker_symbol="BTC",
        quote_ticker_symbol="USD",
        quote_decimals=2,
        name="Bitcoin",
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.001,
        quantity_decimals=3,
        schedule=1,
        candles_timeframe="MIN1",
        enabled=True,
        strategies=[
            StrategyConfig(
                name="SellHigherThanHighestBuyStrategy",
                type=StrategyType.STATIC,
                action=TradeAction.SELL,
                class_name="SellHigherThanHighestBuyStrategy",
                enabled=True,
            )
        ],
    )
    event_bus = MagicMock(spec=EventBus)
    decision_repo = MagicMock()

    account_mgr = MagicMock()
    account_mgr.get_base_balance.return_value = AccountBalance(
        currency="BTC", available_balance=Decimal("1.5")
    )
    account_mgr.get_quote_balance.return_value = AccountBalance(
        currency="USD", available_balance=Decimal("5000")
    )
    market_mgr = MagicMock()
    market_mgr.get_market_data.return_value = MarketData(
        close_price=Decimal("60000"),
        high_price=Decimal("61000"),
        low_price=Decimal("59000"),
        volume=Decimal("150"),
        timestamp=1700000000.0,
        bid_price=Decimal("59990"),
        ask_price=Decimal("60010"),
    )
    market_mgr.get_candles.return_value = []
    fees_mgr = MagicMock()
    fees_mgr.get_instrument_fees.return_value = Fees(
        maker_fee_pct=Decimal("0.001"), taker_fee_pct=Decimal("0.002")
    )
    consensus_mgr = MagicMock()
    consensus_mgr.evaluate.return_value = ConsensusDecision(
        trade_action=TradeAction.SELL,
        ticker_symbol="BTC",
        votes={"SellHigherThanHighestBuyStrategy": True},
        weights={"SellHigherThanHighestBuyStrategy": 1.0},
        factor=1.0,
    )

    created_order = Order(
        uuid="order-sell-456",
        provider_name="BACKTEST",
        ticker_symbol="BTC_USD",
        price=Decimal("60000"),
        quantity="0.5",
        trade_action=TradeAction.SELL,
        created_time=1700000000.0,
        status=OrderStatus.PENDING,
    )
    order_mgr = MagicMock()
    order_mgr.has_outstanding_intent.return_value = False
    order_mgr.open_order.return_value = created_order

    session_mgr = MagicMock()
    session_mgr.get_current_commit_hash.return_value = "commit-sell-456"
    session_mgr.get_trading_context.return_value = TradingContext(
        starting_balance=Decimal("10000.0"),
        ticker_symbol=asset.ticker_symbol,
        exchange=asset.exchange.value,
        position_qty=Decimal("1.5"),
        open_positions=[
            PositionEntry(price=Decimal("50000"), quantity=Decimal("1.5"), timestamp=1700000000.0)
        ],
    )

    container = ManagerContainer(
        account_manager=account_mgr,
        fees_manager=fees_mgr,
        order_manager=order_mgr,
        market_data_manager=market_mgr,
        consensus_manager=consensus_mgr,
        protection_manager=MagicMock(),
        session_manager=session_mgr,
        websocket_manager=MagicMock(),
        rest_manager=MagicMock(),
        portfolio_risk_manager=MagicMock(),
        reconciliation_engine=MagicMock(),
        health_monitor=None,
    )

    executor = TradingExecutor(
        assets=[asset],
        manager_container=container,
        activity_queue=Queue(),
        position_sizer=PositionSizer(),
        strategies_registry=StrategyRegistry(),
        event_bus=event_bus,
        decision_repository=decision_repo,
    )

    executor._process_sell_asset(asset)

    assert decision_repo.save.call_count >= 1
    saved_decision: TradingDecision = decision_repo.save.call_args[0][0]

    assert saved_decision.trade_action == TradeAction.SELL
    assert saved_decision.status == DecisionStatus.EXECUTED
    assert saved_decision.ticker_symbol == "BTC_USD"
    assert saved_decision.commit_hash == "commit-sell-456"
    assert saved_decision.resulting_order_id == "order-sell-456"
    assert saved_decision.consensus_snapshot.quorum is True
