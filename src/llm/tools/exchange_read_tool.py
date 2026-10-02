from __future__ import annotations

from decimal import Decimal
from typing import Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from api.interfaces.timeframe import Timeframe
from src.exchange.interfaces.exchange_rest_manager import ExchangeRestManager
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.helpers.format_helper import FormatHelper


class ExchangeReadOnlyInput(BaseModel):
    operation: str = Field(
        description=(
            "The read-only operation to perform. Supported: "
            "'get_balances', 'get_ticker', 'get_candles', 'get_open_orders', 'get_instrument_fees'"
        )
    )
    exchange: str = Field(
        description="The exchange provider name (e.g. 'CRYPTO_DOT_COM', 'BINANCE', 'KRAKEN')."
    )
    ticker_symbol: Optional[str] = Field(
        default=None,
        description="The ticker symbol (e.g. 'BTC_USD', 'ETH_USD') if required by the operation.",
    )
    timeframe: Optional[str] = Field(
        default="MIN1",
        description="Candle timeframe (e.g. 'MIN1', 'MIN5', 'HOUR1', 'DAY1') for get_candles.",
    )


class ExchangeReadOnlyTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "exchange_read_api"
    description: str = (
        "Safe read-only tool to inspect live exchange data: account balances, ticker prices, "
        "historical candles, open orders, and trading fees directly from exchange APIs."
    )
    args_schema: Type[BaseModel] = ExchangeReadOnlyInput
    rest_manager: ExchangeRestManager

    def __init__(self, rest_manager: ExchangeRestManager):
        super().__init__(rest_manager=rest_manager)

    def _run(  # pylint: disable=arguments-differ
            self,
            operation: str,
            exchange: str,
            ticker_symbol: Optional[str] = None,
            timeframe: Optional[str] = "MIN1",
    ) -> str:
        op = operation.strip().lower()
        ex = exchange.strip().upper()
        symbol = ticker_symbol.strip() if ticker_symbol else None

        try:
            if op in {"get_balances", "balances", "account_balances"}:
                return self._fetch_balances(ex)
            if op in {"get_ticker", "ticker", "get_market_data", "market_data", "price"}:
                if not symbol:
                    return "Error: 'ticker_symbol' is required for get_ticker operation."
                return self._fetch_ticker(ex, symbol)
            if op in {"get_candles", "candles", "ohlc"}:
                if not symbol:
                    return "Error: 'ticker_symbol' is required for get_candles operation."
                return self._fetch_candles(ex, symbol, timeframe or "MIN1")
            if op in {"get_open_orders", "open_orders", "orders"}:
                return self._fetch_open_orders(ex, symbol)
            if op in {"get_instrument_fees", "fees", "fee_rates"}:
                if not symbol:
                    return "Error: 'ticker_symbol' is required for get_instrument_fees operation."
                return self._fetch_fees(ex, symbol)

            return (
                f"Error: Unsupported operation '{operation}'. Supported operations: "
                "'get_balances', 'get_ticker', 'get_candles', 'get_open_orders', 'get_instrument_fees'."
            )
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.error("Error running exchange read operation %s on %s: %s", op, ex, exc, exc_info=True)
            return f"Error executing {op} on {ex}: {exc}"

    def _fetch_balances(self, exchange: str) -> str:
        balances = self.rest_manager.get_account_balance(exchange)
        if not balances:
            return f"No balances returned from exchange {exchange} (or account empty)."
        lines = [f"Live Account Balances for {exchange}:"]
        for b in sorted(balances, key=lambda x: x.currency):
            if b.available_balance > Decimal("0"):
                lines.append(f"  - {b.currency}: {FormatHelper.format_decimal(b.available_balance)}")
        return "\n".join(lines) if len(lines) > 1 else f"All balances on {exchange} are zero."

    def _fetch_ticker(self, exchange: str, ticker_symbol: str) -> str:
        market_data = self.rest_manager.get_market_data(exchange, ticker_symbol)
        if not market_data:
            return f"No market data available for {ticker_symbol} on {exchange}."
        return (
            f"Market Data for {ticker_symbol} on {exchange}:\n"
            f"  Mark Price: ${FormatHelper.format_decimal(market_data.close_price)}\n"
            f"  24h High:   ${FormatHelper.format_decimal(market_data.high_price)}\n"
            f"  24h Low:    ${FormatHelper.format_decimal(market_data.low_price)}\n"
            f"  24h Volume: {FormatHelper.format_decimal(market_data.volume)}\n"
            f"  Timestamp:  {market_data.timestamp}"
        )

    def _fetch_candles(self, exchange: str, ticker_symbol: str, timeframe_str: str) -> str:
        tf_name = timeframe_str.upper()
        tf = Timeframe[tf_name] if tf_name in Timeframe.__members__ else Timeframe.MIN1
        candles = self.rest_manager.get_candles(exchange, ticker_symbol, tf)
        if not candles:
            return f"No candles available for {ticker_symbol} ({tf.value}) on {exchange}."
        recent = candles[-5:] if len(candles) > 5 else candles
        lines = [f"Recent Candles for {ticker_symbol} ({tf.value}) on {exchange} ({len(candles)} total, showing last {len(recent)}):"]
        for c in recent:
            ts = c.start_time
            lines.append(
                f"  - Time: {ts} | O: {FormatHelper.format_decimal(c.open)} | H: {FormatHelper.format_decimal(c.high)} | "
                f"L: {FormatHelper.format_decimal(c.low)} | C: {FormatHelper.format_decimal(c.close)}"
            )
        return "\n".join(lines)

    def _fetch_open_orders(self, exchange: str, ticker_symbol: Optional[str]) -> str:
        orders = self.rest_manager.get_open_orders(exchange, ticker_symbol)
        if not orders:
            sym_text = f" for {ticker_symbol}" if ticker_symbol else ""
            return f"No open orders on {exchange}{sym_text}."
        lines = [f"Open Orders on {exchange} ({len(orders)} active):"]
        for o in orders:
            lines.append(
                f"  - UUID: {o.uuid} | Symbol: {o.ticker_symbol} | Side: {o.trade_action.value} | "
                f"Qty: {o.quantity} | Price: {o.price} | Status: {o.status}"
            )
        return "\n".join(lines)

    def _fetch_fees(self, exchange: str, ticker_symbol: str) -> str:
        fees = self.rest_manager.get_instrument_fees(exchange, ticker_symbol)
        if not fees:
            return f"No fee information available for {ticker_symbol} on {exchange}."
        maker_pct = fees.maker_fee_pct * Decimal("100")
        taker_pct = fees.taker_fee_pct * Decimal("100")
        return (
            f"Trading Fees for {ticker_symbol} on {exchange}:\n"
            f"  Maker Fee: {FormatHelper.format_decimal(maker_pct)}%\n"
            f"  Taker Fee: {FormatHelper.format_decimal(taker_pct)}%"
        )
