from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.llm.tools.trading_context_tool import format_decimal
from src.trading.orders.order_manager import OrderManager


class OpenOrdersInput(BaseModel):
    exchange: str = Field(
        default=None,
        description=(
            "Optional exchange/provider name (e.g., 'CRYPTO_DOT_COM', 'CCXT_BINANCE'). "
            "Omit to query all configured exchanges for open orders."
        )
    )
    ticker_symbol: str = Field(
        default=None,
        description=(
            "Optional single ticker symbol of the asset (e.g., 'BTC_USD'). Do not pass a list. "
            "Omit to check all open orders."
        )
    )


class GetOpenOrdersTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_open_orders"
    description: str = (
        "Queries the exchange(s) for the latest status of open (pending) orders. "
        "Optionally filters by a single ticker symbol and/or exchange. "
        "Returns the open orders with their current status."
    )
    args_schema: Type[BaseModel] = OpenOrdersInput
    order_manager: OrderManager
    assets: list = []

    def __init__(self, order_manager: OrderManager, assets: list):
        super().__init__(
            order_manager=order_manager,
            assets=assets
        )

    def _run(self, exchange: str = None, ticker_symbol: str = None) -> str:
        target_exchange = exchange.strip() if exchange else None
        target_symbol = ticker_symbol.strip() if ticker_symbol else None

        exchanges = set()
        for asset in self.assets:
            if target_exchange and asset.exchange.value != target_exchange:
                continue
            if target_symbol and asset.ticker_symbol != target_symbol:
                continue
            exchanges.add(asset.exchange.value)
        if target_exchange:
            exchanges.add(target_exchange)

        if not exchanges:
            return "Error: No configured exchanges to query for open orders."

        open_orders = []
        for current_exchange in sorted(exchanges):
            try:
                open_orders.extend(
                    self.order_manager.get_open_orders(current_exchange, target_symbol)
                )
            except Exception as e:
                err_msg = f"Error fetching open orders from {current_exchange}: {e}"
                self.app_logger.error(err_msg, exc_info=True)
                return err_msg

        if not open_orders:
            scope = f" for {target_symbol}" if target_symbol else ""
            exchange_scope = f" on {target_exchange}" if target_exchange else ""
            self.app_logger.info(f"No open orders found{scope}{exchange_scope}.")
            return f"No open orders found{scope}{exchange_scope}."

        orders_str_list = []
        for order in open_orders:
            order_str = (
                f"  Order({order.uuid}): {order.ticker_symbol} {order.trade_action.value} "
                f"qty={format_decimal(order.quantity)} price={format_decimal(order.price)} "
                f"status={order.status.value} exchange={order.provider_name}"
            )
            orders_str_list.append(order_str)

        scope = f" for {target_symbol}" if target_symbol else ""
        exchange_scope = f" on {target_exchange}" if target_exchange else ""
        report = (
            f"Open Orders{scope}{exchange_scope} ({len(open_orders)}):\n"
            + "\n".join(orders_str_list)
        )
        self.app_logger.info(f"Open orders for LLM{scope}{exchange_scope}:")
        self.app_logger.warning(report)
        return report
