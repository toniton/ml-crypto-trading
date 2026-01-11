from dataclasses import dataclass

from src.trading.accounts.account_manager import AccountManager
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.session.session_manager import SessionManager
from src.trading.fees.fees_manager import FeesManager
from src.trading.markets.market_data_manager import MarketDataManager
from src.trading.orders.order_manager import OrderManager
from src.trading.protection.protection_manager import ProtectionManager
from src.clients.websocket_manager import WebSocketManager


@dataclass(frozen=True)
class ManagerContainer:
    account_manager: AccountManager
    fees_manager: FeesManager
    order_manager: OrderManager
    market_data_manager: MarketDataManager
    consensus_manager: ConsensusManager
    protection_manager: ProtectionManager
    session_manager: SessionManager
    websocket_manager: WebSocketManager
