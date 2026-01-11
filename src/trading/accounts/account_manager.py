import time
from collections import defaultdict

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.core.registries.asset_schedule_registry import AssetScheduleRegistry
from src.core.registries.rest_client_registry import RestClientRegistry
from src.core.registries.websocket_registry import WebSocketRegistry
from src.clients.websocket_manager import WebSocketManager
from src.trading.session.session_manager import SessionManager


class AccountManager(ApplicationLoggingMixin, RestClientRegistry, WebSocketRegistry):

    def __init__(self, assets: list[Asset], websocket_manager: WebSocketManager):
        super().__init__()
        self.assets = assets
        self._websocket_manager = websocket_manager
        self.balances = {}
        self.last_balance_updates = defaultdict(dict)

    def _cache_balances(self, provider_name: str, balances: list[AccountBalance]) -> None:
        if provider_name not in self.balances:
            self.balances[provider_name] = {}

        for balance in balances:
            self.balances[provider_name][balance.currency] = balance
            self.last_balance_updates[provider_name][balance.currency] = time.time()

        self.app_logger.debug(f"Updated balances for {provider_name}: {self.balances[provider_name]}")

    def init_websocket(self):
        for provider_name in self.websockets:
            self._websocket_manager.subscribe_account_balance(
                exchange=provider_name,
                callback=lambda data, provider=provider_name: self._cache_balances(provider, data)
            )

    def shutdown(self):
        for provider_name in self.websockets:
            self._websocket_manager.unsubscribe_account_balance(exchange=provider_name)

    def init_account_balances(self, session_manager: SessionManager):
        for asset in self.assets:
            exchange = asset.exchange
            try:
                opening_balance = self.get_balance(asset, exchange.value)
                session_manager.init_asset_balance(asset, opening_balance.available_balance)
            except Exception:
                self.app_logger.error(f"Unable to initialize account balance for {asset} from {exchange}",
                                      exc_info=True)

    def get_balance(self, asset: Asset, provider_name: str) -> AccountBalance:
        currency_symbol = asset.quote_ticker_symbol
        last_update = self.last_balance_updates.get(provider_name, {}).get(currency_symbol)
        should_refresh = (
                last_update is None or
                (time.time() - last_update) > AssetScheduleRegistry.UNIT_SECONDS[asset.schedule]
        )
        if should_refresh:
            provider = self.get_client(provider_name)
            data = provider.get_account_balance()
            self._cache_balances(provider_name, data)

        return self.balances.get(provider_name, {}).get(currency_symbol) or AccountBalance(currency_symbol, 0)

    def close_account_balances(self, session_manager: SessionManager):
        for asset in self.assets:
            exchange = asset.exchange
            try:
                closing_balance = self.get_balance(asset, exchange.value)
                session_manager.close_asset_balance(asset.key, closing_balance.available_balance)
            except Exception:
                self.app_logger.error(f"Unable to close account balance for {asset} from {exchange}",
                                      exc_info=True)
