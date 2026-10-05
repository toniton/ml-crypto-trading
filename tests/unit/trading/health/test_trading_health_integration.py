from datetime import datetime, timezone
from decimal import Decimal
from queue import Queue
from unittest.mock import MagicMock

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from src.core.interfaces.event_bus import EventBus
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.events.domain_events import DecisionRejectedEvent, DecisionRejectedReason
from src.trading.health import (
    HealthMonitor,
    HealthObservation,
    HealthScope,
    RecoveryConfig,
    TradingHealthCondition,
    TradingHealthState,
)
from src.trading.managers.manager_container import ManagerContainer
from src.trading.strategies.strategy_registry import StrategyRegistry
from src.trading.trading_executor import TradingExecutor


def test_trading_executor_blocks_order_when_paused():
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
    )
    event_bus = MagicMock(spec=EventBus)
    health_monitor = HealthMonitor.create(
        event_bus=event_bus,
        recovery_config=RecoveryConfig(),
        initial_state=TradingHealthState.TRADING,
    )

    # Put health monitor into PAUSED
    health_monitor.report_observation(
        HealthObservation(
            source="test",
            condition=TradingHealthCondition.EXCHANGE_UNAVAILABLE,
            scope=HealthScope.global_scope(),
            healthy=False,
            observed_at=datetime.now(timezone.utc),
        )
    )
    assert health_monitor.current_state == TradingHealthState.PAUSED

    # Set up mocks for executor
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
        timestamp=datetime.now(timezone.utc).timestamp(),
    )
    market_mgr.get_candles.return_value = []
    fees_mgr = MagicMock()
    fees_mgr.get_instrument_fees.return_value = Fees(maker_fee_pct=Decimal("0.001"), taker_fee_pct=Decimal("0.002"))
    consensus_mgr = MagicMock()
    decision = MagicMock()
    decision.quorum = True
    decision.true_count = 3
    decision.total = 3
    consensus_mgr.evaluate.return_value = decision

    order_mgr = MagicMock()
    order_mgr.has_outstanding_intent.return_value = False

    portfolio_risk_mgr = MagicMock()
    portfolio_risk_mgr.can_trade.return_value = (True, None)

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
        health_monitor=health_monitor,
    )

    executor = TradingExecutor(
        assets=[asset],
        manager_container=container,
        activity_queue=Queue(),
        dynamic_quantity=None,
        strategies_registry=StrategyRegistry(),
        event_bus=event_bus,
    )

    # Process buy asset
    executor._process_buy_asset(asset)

    # Order manager should NOT have opened any order
    order_mgr.open_order.assert_not_called()

    # Event bus should have received DecisionRejectedEvent with reason HEALTH_HALT
    published_events = [call.args[0] for call in event_bus.publish.call_args_list]
    health_halt_events = [
        e for e in published_events
        if isinstance(e, DecisionRejectedEvent) and e.reason == DecisionRejectedReason.HEALTH_HALT.value
    ]
    assert len(health_halt_events) == 1
    assert health_halt_events[0].symbol == "BTC_USD"
