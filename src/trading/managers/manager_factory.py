from __future__ import annotations

from typing import Tuple

from src.exchange.factories.client_factory import ClientFactory
from src.trading.accounts.account_manager import AccountManager
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.fees.fees_manager import FeesManager
from src.trading.managers.manager_container import ManagerContainer
from src.trading.markets.market_data_manager import MarketDataManager
from src.trading.orders.order_manager import OrderManager
from src.trading.protection.protection_manager import ProtectionManager
from src.trading.session.in_memory_trading_journal import InMemoryTradingJournal
from src.trading.session.session_manager import SessionManager


class ManagerFactory:
    @staticmethod
    def build_manager_container(
            database_manager,
            assets,
            is_simulated: bool = False,
            is_backtest: bool = False,
            event_bus=None,
    ) -> Tuple[ManagerContainer, InMemoryTradingJournal]:
        trading_journal = InMemoryTradingJournal()
        websocket_manager = ClientFactory.create_websocket_manager(is_simulated)
        rest_manager = ClientFactory.create_rest_manager(is_simulated)
        order_manager = OrderManager(
            database_manager, trading_journal, rest_manager, websocket_manager, is_backtest
        )

        container = ManagerContainer(
            account_manager=AccountManager(assets, rest_manager, websocket_manager),
            fees_manager=FeesManager(assets, rest_manager),
            order_manager=order_manager,
            market_data_manager=MarketDataManager(rest_manager, websocket_manager, event_bus),
            consensus_manager=ConsensusManager(),
            protection_manager=ProtectionManager(),
            session_manager=SessionManager(),
            websocket_manager=websocket_manager,
            rest_manager=rest_manager,
        )
        return container, trading_journal
