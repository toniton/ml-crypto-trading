from __future__ import annotations

import threading
import time
from collections import defaultdict
from decimal import Decimal

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from src.core.interfaces.event_bus import EventBus
from src.exchange.managers.rest_manager import RestManager
from src.exchange.managers.websocket_manager import WebSocketManager
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.accounts.account_state import AccountState
from src.trading.events import BalanceChangedEvent
from src.trading.session.session_manager import SessionManager


class AccountManager(ApplicationLoggingMixin):
    def __init__(
            self,
            assets: list[Asset],
            rest_manager: RestManager,
            websocket_manager: WebSocketManager,
            session_manager: SessionManager,
            event_bus: EventBus,
    ):
        self.assets = assets
        self._rest_manager = rest_manager
        self._websocket_manager = websocket_manager
        self._session_manager = session_manager
        self._event_bus = event_bus
        self.account_states: dict[str, AccountState] = {}
        self.balances: dict[str, dict[str, AccountBalance]] = {}
        self.last_balance_updates: dict[str, dict[str, float]] = defaultdict(dict)
        self._lock = threading.Lock()

    def get_account_state(self, exchange: str) -> AccountState:
        with self._lock:
            ex_key = exchange.upper()
            if ex_key not in self.account_states:
                self.account_states[ex_key] = AccountState(exchange=ex_key)
            return self.account_states[ex_key]

    def _cache_balances(
            self,
            provider_name: str,
            balances: list[AccountBalance],
            source: str = "WS",
            reason: str = "UPDATE",
    ) -> None:
        events_to_publish: list[BalanceChangedEvent] = []

        with self._lock:
            ex_key = provider_name.upper()
            if ex_key not in self.account_states:
                self.account_states[ex_key] = AccountState(exchange=ex_key)
            account_state = self.account_states[ex_key]

            if ex_key not in self.balances:
                self.balances[ex_key] = {}

            for balance in balances:
                curr_key = balance.currency.upper()
                new_state, prev_state = account_state.update_balance(
                    currency=curr_key,
                    available=balance.available_balance,
                    source=source,
                )

                self.balances[ex_key][curr_key] = balance
                self.last_balance_updates[ex_key][curr_key] = time.time()

                # Emit event on state transition or first observation
                has_changed = (
                        prev_state is None
                        or prev_state.has_changed(new_state.available, new_state.total)
                )
                if has_changed:
                    event = BalanceChangedEvent(
                        exchange=ex_key,
                        currency=curr_key,
                        available=new_state.available,
                        total=new_state.total,
                        reserved=new_state.reserved,
                        previous_available=prev_state.available if prev_state else None,
                        previous_total=prev_state.total if prev_state else None,
                        source=source,
                        reason=reason,
                        version=new_state.version,
                    )
                    events_to_publish.append(event)
                    self.app_logger.info(
                        "Balance changed on %s for %s: %s -> %s (total: %s, source: %s)",
                        ex_key,
                        curr_key,
                        prev_state.available if prev_state else "N/A",
                        new_state.available,
                        new_state.total,
                        source,
                    )

        for event in events_to_publish:
            self._event_bus.publish(event)

        self.app_logger.debug(f"Updated canonical balances for {provider_name} via {source}: {len(balances)} items")

    def init_websocket(self) -> None:
        subscribed_exchanges = set()
        for asset in self.assets:
            exchange = asset.exchange.value
            if exchange not in subscribed_exchanges:
                self._websocket_manager.subscribe_account_balance(
                    exchange=exchange,
                    callback=lambda data, provider=exchange: self._cache_balances(provider, data, source="WS")
                )
                subscribed_exchanges.add(exchange)

    def shutdown(self) -> None:
        for provider_name in self._websocket_manager.get_registered_services():
            self._websocket_manager.unsubscribe_account_balance(exchange=provider_name)

    def init_asset_balance(self, asset: Asset) -> bool:
        if self._session_manager.get_trading_context(asset.key) is not None:
            return True
        try:
            opening_balance = self.get_quote_balance(asset, asset.exchange.value)
            base_balance = self.get_base_balance(asset, asset.exchange.value)
            base_qty = base_balance.available_balance if base_balance else Decimal("0")
            if base_qty > Decimal("0"):
                market_data = self._rest_manager.get_market_data(
                    asset.exchange.value, asset.ticker_symbol
                )
                self._session_manager.init_asset_balance(
                    asset,
                    opening_balance.available_balance,
                    initial_position_qty=base_qty,
                    initial_entry_price=market_data.close_price,
                )
            else:
                self._session_manager.init_asset_balance(asset, opening_balance.available_balance)
            return True
        except Exception:
            self.app_logger.error(
                f"Unable to initialize account balance for {asset} from {asset.exchange}",
                exc_info=True,
            )
            return False

    def init_account_balances(self) -> None:
        for asset in self.assets:
            self.init_asset_balance(asset)

    def get_base_balance(self, asset: Asset, provider_name: str) -> AccountBalance:
        currency_symbol = str(asset.base_ticker_symbol)
        return self._get_balance(currency_symbol, asset.schedule, provider_name)

    def get_quote_balance(self, asset: Asset, provider_name: str) -> AccountBalance:
        currency_symbol = str(asset.quote_ticker_symbol)
        return self._get_balance(currency_symbol, asset.schedule, provider_name)

    def reconcile_account_balances(self, provider_name: str) -> list[AccountBalance]:
        try:
            data = self._rest_manager.get_account_balance(provider_name, force_refresh=True)
        except TypeError:
            data = self._rest_manager.get_account_balance(provider_name)
        self._cache_balances(provider_name, data, source="REST_RECONCILIATION", reason="SNAPSHOT")
        with self._lock:
            ex_key = provider_name.upper()
            if ex_key in self.account_states:
                self.account_states[ex_key].last_reconciliation_time = time.time()
        return data

    def _get_balance(self, currency_symbol: str, schedule: AssetSchedule, provider_name: str) -> AccountBalance:
        curr_key = currency_symbol.upper()
        ex_key = provider_name.upper()

        with self._lock:
            should_refresh = ex_key not in self.balances or curr_key not in self.balances[ex_key]

        if should_refresh:
            self.reconcile_account_balances(provider_name)

        with self._lock:
            if ex_key in self.balances and curr_key in self.balances[ex_key]:
                return self.balances[ex_key][curr_key]
            return AccountBalance(currency_symbol, Decimal(0))

    def close_account_balances(self) -> None:
        for asset in self.assets:
            exchange = asset.exchange
            try:
                closing_balance = self.get_quote_balance(asset, exchange.value)
                self._session_manager.close_asset_balance(asset.key, closing_balance.available_balance)
            except Exception:
                self.app_logger.error(
                    f"Unable to close account balance for {asset} from {exchange}",
                    exc_info=True,
                )
