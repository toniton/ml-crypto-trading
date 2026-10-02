from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from src.events.message_event_bus import CallbackSubscription, MessageEventBus
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.exchange.managers.rest_manager import RestManager
from src.exchange.managers.websocket_manager import WebSocketManager
from src.trading.accounts.account_manager import AccountManager
from src.trading.accounts.account_state import AccountState, CurrencyBalanceState
from src.trading.events import BalanceChangedEvent
from src.trading.protection.portfolio_risk_manager import PortfolioRiskManager
from src.trading.session.session_manager import SessionManager


def _create_sample_asset(symbol="BTC_USD", exchange="CRYPTO_DOT_COM", quote="USD", base="BTC") -> Asset:
    return Asset(
        exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM if exchange == "CRYPTO_DOT_COM" else ExchangeProvidersEnum.CCXT_BINANCE,
        schedule=AssetSchedule.EVERY_MINUTE,
        quote_ticker_symbol=quote,
        base_ticker_symbol=base,
        quote_decimals=2,
        name=symbol,
        min_quantity=0.01,
        quantity_decimals=4,
        candles_timeframe=Timeframe.MIN1,
    )


class TestAccountState:
    def test_update_balance_and_versioning(self):
        state = AccountState(exchange="CRYPTO_DOT_COM")
        curr, prev = state.update_balance("USD", available=Decimal("1000.00"), total=Decimal("1200.00"), source="WS")

        assert prev is None
        assert curr.version == 1
        assert curr.available == Decimal("1000.00")
        assert curr.total == Decimal("1200.00")
        assert curr.reserved == Decimal("200.00")

        # Second update
        curr2, prev2 = state.update_balance("USD", available=Decimal("950.00"), total=Decimal("1200.00"), source="WS")
        assert prev2 is not None
        assert prev2.version == 1
        assert curr2.version == 2
        assert curr2.available == Decimal("950.00")
        assert curr2.reserved == Decimal("250.00")

    def test_delta_detection(self):
        curr = CurrencyBalanceState(currency="USD", available=Decimal("100"), total=Decimal("100"), reserved=Decimal("0"))
        assert not curr.has_changed(Decimal("100"), Decimal("100"))
        assert curr.has_changed(Decimal("90"), Decimal("100"))
        assert curr.has_changed(Decimal("100"), Decimal("110"))


class TestAccountManagerAndEventDrivenSync:
    def test_ws_balance_update_emits_event_and_updates_portfolio(self):
        event_bus = MessageEventBus()
        asset = _create_sample_asset()

        rest_mgr = MagicMock(spec=RestManager)
        ws_mgr = MagicMock(spec=WebSocketManager)
        session_mgr = SessionManager(event_bus=event_bus)
        session_mgr.create_session("sess-1").start_session()
        session_mgr.init_asset_balance(asset, starting_balance=Decimal("500.00"))

        risk_mgr = PortfolioRiskManager(assets=[asset], event_bus=event_bus)
        portfolio = risk_mgr.get_portfolio("CRYPTO_DOT_COM", "USD")

        account_mgr = AccountManager(
            assets=[asset],
            rest_manager=rest_mgr,
            websocket_manager=ws_mgr,
            session_manager=session_mgr,
            event_bus=event_bus,
        )

        # Simulate WS incoming balance payload
        account_mgr._cache_balances(
            "CRYPTO_DOT_COM",
            [AccountBalance(currency="USD", available_balance=Decimal("750.00"))],
            source="WS",
        )

        # Verify canonical account state
        state = account_mgr.get_account_state("CRYPTO_DOT_COM")
        usd_bal = state.get_balance("USD")
        assert usd_bal is not None
        assert usd_bal.available == Decimal("750.00")
        assert usd_bal.version == 1

        # Verify PortfolioRiskManager updated via EventBus
        assert portfolio.total_cash == Decimal("750.00")
        assert portfolio.available_cash == Decimal("750.00")

        # Verify SessionManager context updated via EventBus
        ctx = session_mgr.get_trading_context(asset.key)
        assert ctx.available_balance == Decimal("750.00")

    def test_deduplication_of_identical_balance_frames(self):
        event_bus = MessageEventBus()
        events_received = []
        event_bus.subscribe(
            BalanceChangedEvent.__name__,
            CallbackSubscription(lambda e: events_received.append(e)),
        )

        asset = _create_sample_asset()
        account_mgr = AccountManager(
            assets=[asset],
            rest_manager=MagicMock(spec=RestManager),
            websocket_manager=MagicMock(spec=WebSocketManager),
            session_manager=MagicMock(spec=SessionManager),
            event_bus=event_bus,
        )

        # Frame 1: initial observation
        account_mgr._cache_balances("CRYPTO_DOT_COM", [AccountBalance("USD", Decimal("1000.00"))])
        assert len(events_received) == 1

        # Frame 2: duplicate identical frame -> no event published
        account_mgr._cache_balances("CRYPTO_DOT_COM", [AccountBalance("USD", Decimal("1000.00"))])
        assert len(events_received) == 1

        # Frame 3: value change -> event published
        account_mgr._cache_balances("CRYPTO_DOT_COM", [AccountBalance("USD", Decimal("900.00"))])
        assert len(events_received) == 2
        assert events_received[1].available == Decimal("900.00")
        assert events_received[1].previous_available == Decimal("1000.00")

    def test_rest_reconciliation_updates_canonical_state(self):
        event_bus = MessageEventBus()
        asset = _create_sample_asset()

        rest_mgr = MagicMock(spec=RestManager)
        rest_mgr.get_account_balance.return_value = [
            AccountBalance("USD", Decimal("2500.00")),
            AccountBalance("BTC", Decimal("0.05")),
        ]

        account_mgr = AccountManager(
            assets=[asset],
            rest_manager=rest_mgr,
            websocket_manager=MagicMock(spec=WebSocketManager),
            session_manager=MagicMock(spec=SessionManager),
            event_bus=event_bus,
        )

        reconciled = account_mgr.reconcile_account_balances("CRYPTO_DOT_COM")
        assert len(reconciled) == 2

        state = account_mgr.get_account_state("CRYPTO_DOT_COM")
        assert state.get_balance("USD").available == Decimal("2500.00")
        assert state.get_balance("USD").source == "REST_RECONCILIATION"
        assert state.last_reconciliation_time > 0

    def test_reconciliation_cooldown_prevents_rest_spam(self):
        asset = _create_sample_asset()
        rest_mgr = MagicMock(spec=RestManager)
        rest_mgr.get_account_balance.return_value = [
            AccountBalance("USD", Decimal("100.00")),
        ]

        account_mgr = AccountManager(
            assets=[asset],
            rest_manager=rest_mgr,
            websocket_manager=MagicMock(spec=WebSocketManager),
            session_manager=MagicMock(spec=SessionManager),
            event_bus=MessageEventBus(),
        )

        # First call fetches initial balance via REST
        bal1 = account_mgr.get_quote_balance(asset, "CRYPTO_DOT_COM")
        assert bal1.available_balance == Decimal("100.00")
        assert rest_mgr.get_account_balance.call_count == 1

        # Subsequent calls within cooldown period reuse cached state without calling REST
        for _ in range(50):
            bal = account_mgr.get_quote_balance(asset, "CRYPTO_DOT_COM")
            assert bal.available_balance == Decimal("100.00")

        assert rest_mgr.get_account_balance.call_count == 1

