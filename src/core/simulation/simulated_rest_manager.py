import time
from decimal import Decimal
from typing import Any, List

from api.interfaces.account_balance import AccountBalance
from api.interfaces.fees import Fees
from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.clients.rest_manager import RestManager
from src.core.simulation.simulated_account import SimulatedAccount


class SimulatedRestManager(RestManager):
    def __init__(self, account: SimulatedAccount):
        super().__init__()
        self._account = account

    def get_account_balance(self, exchange: str) -> List[AccountBalance]:
        balances = []
        for currency, amount in self._account.get_balances():
            balances.append(AccountBalance(currency=currency, available_balance=amount))
        return balances

    def get_account_fees(self, exchange: str) -> Fees:
        return Fees(maker_fee_pct=Decimal("0.0"), taker_fee_pct=Decimal("0.0"))

    def get_instrument_fees(self, exchange: str, ticker_symbol: str) -> Fees:
        return Fees(maker_fee_pct=Decimal("0.0"), taker_fee_pct=Decimal("0.0"))

    def get_order(self, exchange: str, uuid: str) -> Any:
        return self._account.get_order(uuid)

    def place_order(
            self,
            exchange: str,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: Decimal,
            trade_action: TradeAction
    ) -> None:
        order = Order(
            uuid=uuid,
            provider_name=exchange,
            ticker_symbol=ticker_symbol,
            quantity=quantity,
            price=price,
            trade_action=trade_action,
            created_time=time.time(),
            status=OrderStatus.PENDING
        )
        self._account.add_order(order)
        self._account.execute_order(order)

    def cancel_order(self, exchange: str, uuid: str) -> None:
        self._account.cancel_order(uuid)
