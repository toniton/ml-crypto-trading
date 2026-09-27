import threading
import time
from collections import defaultdict
from decimal import Decimal

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from src.exchange.managers.rest_manager import RestManager
from src.exchange.managers.websocket_manager import WebSocketManager
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.scheduling.asset_schedule_registry import AssetScheduleRegistry
from src.trading.session.session_manager import SessionManager


class AccountManager(ApplicationLoggingMixin):

    def __init__(
            self,
            assets: list[Asset],
            rest_manager: RestManager,
            websocket_manager: WebSocketManager,
            session_manager: SessionManager,
    ):
        self.assets = assets
        self._rest_manager = rest_manager
        self._websocket_manager = websocket_manager
        self._session_manager = session_manager
        self.balances: dict[str, dict[str, AccountBalance]] = {}
        self.last_balance_updates: dict[str, dict[str, float]] = defaultdict(dict)
        self._lock = threading.Lock()

    def _cache_balances(self, provider_name: str, balances: list[AccountBalance]) -> None:
        with self._lock:
            if provider_name not in self.balances:
                self.balances[provider_name] = {}

            for balance in balances:
                self.balances[provider_name][balance.currency] = balance
                self.last_balance_updates[provider_name][balance.currency] = time.time()

        self.app_logger.debug(f"Updated balances for {provider_name}: {self.balances[provider_name]}")

    def init_websocket(self):
        subscribed_exchanges = set()
        for asset in self.assets:
            exchange = asset.exchange.value
            if exchange not in subscribed_exchanges:
                self._websocket_manager.subscribe_account_balance(
                    exchange=exchange,
                    callback=lambda data, provider=exchange: self._cache_balances(provider, data)
                )
                subscribed_exchanges.add(exchange)

    def shutdown(self):
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

    def _get_balance(self, currency_symbol: str, schedule: AssetSchedule, provider_name: str) -> AccountBalance:
        with self._lock:
            last_update = self.last_balance_updates.get(provider_name, {}).get(currency_symbol)
            should_refresh = (
                    last_update is None or
                    (time.time() - last_update) > AssetScheduleRegistry.UNIT_SECONDS[schedule]
            )

        if should_refresh:
            data = self._rest_manager.get_account_balance(provider_name)
            self._cache_balances(provider_name, data)

        with self._lock:
            return self.balances.get(provider_name, {}).get(currency_symbol) or AccountBalance(currency_symbol,
                                                                                               Decimal(0))

    def close_account_balances(self) -> None:
        for asset in self.assets:
            exchange = asset.exchange
            try:
                closing_balance = self.get_quote_balance(asset, exchange.value)
                self._session_manager.close_asset_balance(asset.key, closing_balance.available_balance)
            except Exception:
                self.app_logger.error(f"Unable to close account balance for {asset} from {exchange}",
                                      exc_info=True)
