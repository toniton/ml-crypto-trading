from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from api.interfaces.trade_action import OrderStatus, TradeAction


@dataclass
class PendingOrder:
    order_uuid: str
    ticker_symbol: str
    trade_action: TradeAction
    quantity: Decimal
    requested_price: Decimal
    signal_at: float
    submitted_at: float
    eligible_at: float
    execution_timestamp: Optional[int] = None


@dataclass
class ExecutionResult:  # pylint: disable=too-many-instance-attributes
    order_uuid: str
    ticker_symbol: str
    trade_action: TradeAction
    status: OrderStatus
    requested_price: Decimal
    market_price: Decimal
    execution_price: Decimal
    requested_quantity: Decimal
    executed_quantity: Decimal
    slippage_per_unit: Decimal
    slippage_cost: Decimal
    fee: Decimal
    signal_at: float
    submitted_at: float
    eligible_at: float
    executed_at: float
