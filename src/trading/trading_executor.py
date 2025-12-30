from __future__ import annotations

import logging
import time
from queue import Queue

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.trading.helpers.portfolio_helper import PortfolioHelper
from src.core.managers.manager_container import ManagerContainer
from src.trading.orders.order_helper import OrderHelper


class TradingExecutor:
    def __init__(
            self,
            assets: list[Asset],
            manager_container: ManagerContainer,
            activity_queue: Queue
    ):
        self.assets = assets
        self.account_manager = manager_container.account_manager
        self.fees_manager = manager_container.fees_manager
        self.order_manager = manager_container.order_manager
        self.market_data_manager = manager_container.market_data_manager
        self.consensus_manager = manager_container.consensus_manager
        self.trading_context_manager = manager_container.trading_context_manager
        self.protection_manager = manager_container.protection_manager
        self.activity_queue = activity_queue

    def init_application(self):
        self.account_manager.init_account_balances(self.trading_context_manager)
        self.fees_manager.init_account_fees()
        self.account_manager.init_websocket()
        self.order_manager.init_websocket(self.assets)
        self.market_data_manager.init_websocket()

    def _fetch_market_data(self, asset: Asset) -> MarketData:
        market_data = self.market_data_manager.get_latest_marketdata(asset.key)
        return market_data or self.market_data_manager.get_market_data(asset.ticker_symbol, asset.exchange.value)

    def _should_trade(self, asset: Asset, action: TradeAction, market_data: MarketData, candles: list[Candle]) -> bool:
        trading_context = self.trading_context_manager.get_trading_context(asset.key)

        if not self.protection_manager.can_trade(asset.key, action, trading_context, market_data):
            return False

        consensus_result = self.consensus_manager.get_quorum(
            action, asset.ticker_symbol, trading_context, market_data, candles
        )
        logging.warning([
            f"Consensus={consensus_result} for asset={asset}"
        ])
        return bool(consensus_result)

    def _prepare_trade_context(self, asset: Asset) -> tuple[AccountBalance, MarketData, list[Candle], Fees]:
        currency_symbol = asset.quote_ticker_symbol
        account_balance = self.account_manager.get_balance(currency_symbol, asset.exchange.value)
        if account_balance.available_balance <= 0:
            raise ValueError(f"Insufficient balance for {currency_symbol}: ${account_balance.available_balance}")

        market_data = self._fetch_market_data(asset)
        logging.warning([
            f"Fetched market data for Asset. Asset={asset} MarketData={market_data}"
        ])
        fees = self.fees_manager.get_instrument_fees(asset.ticker_symbol, asset.exchange.value)
        candles = self.market_data_manager.get_candles(
            asset.exchange.value, asset.ticker_symbol, asset.candles_timeframe
        )

        return account_balance, market_data, candles, fees

    def create_buy_order(self, assets: list[Asset]):
        for asset in assets:
            try:
                account_balance, market_data, candles, fees = self._prepare_trade_context(asset)
                self.trading_context_manager.update_trading_context(asset.key, account_balance.available_balance)
                if not self._should_trade(asset, TradeAction.BUY, market_data, candles):
                    logging.info(f"No consensus to buy {asset.ticker_symbol}")
                    continue

                price = market_data.close_price
                price = float(price) + (float(price) * fees.maker_fee_pct * 0.01)
                price = format(round(price, asset.decimal_places), f".{asset.decimal_places}f")

                logging.warning([
                    f"Fetched price for Asset. Asset={asset} Price={price}",
                    f"Fees={fees}",
                    f"Available balance={account_balance.available_balance}"
                ])
                quantity = format(asset.min_quantity, "f")
                buy_order = self.order_manager.open_order(
                    ticker_symbol=asset.ticker_symbol,
                    quantity=quantity,
                    price=str(price),
                    provider_name=asset.exchange.value,
                    trade_action=TradeAction.BUY,
                    timestamp=market_data.timestamp
                )
                self.activity_queue.put_nowait(buy_order.model_dump_json())
                self.trading_context_manager.record_buy(asset.key, buy_order)
            except Exception as exc:
                logging.error([f"Error occurred processing asset. Asset={asset}", exc])

    def check_unclosed_orders(self, assets: list[Asset]):
        for asset in assets:
            try:
                trading_context = self.trading_context_manager.get_trading_context(asset.key)
                if not trading_context.open_positions:
                    logging.info([f"No open positions for asset. Asset={asset}"])
                    continue
                _, market_data, candles, fees = self._prepare_trade_context(asset)
                current_price = market_data.close_price

                logging.warning([f"Fetched current_price for {asset}. Price={current_price}", f"Fees={fees}"])

                if not self._should_trade(asset, TradeAction.SELL, market_data, candles):
                    continue

                open_orders: list[Order] = sorted(
                    filter(OrderHelper.less_than_price_filter(current_price), trading_context.open_positions),
                    key=lambda o, _current_price=market_data.close_price: (
                            (float(_current_price) - float(o.price)) / float(o.price)
                    )
                )

                best_order: Order | None = next(iter(open_orders), None)
                if best_order:
                    sell_order = self.order_manager.open_order(
                        uuid=best_order.uuid, price=current_price, trade_action=TradeAction.SELL,
                        quantity=best_order.quantity, provider_name=best_order.provider_name,
                        ticker_symbol=best_order.ticker_symbol, timestamp=market_data.timestamp
                    )
                    self.activity_queue.put_nowait(sell_order.model_dump_json())
                    self.trading_context_manager.record_sell(asset.key, sell_order)

            except Exception as exc:
                logging.error([f"Error occurred finalizing asset. Asset={asset}", exc])
        logging.info(["Threading..., sleeping...."])

    def backfill_trading_context(self):
        # Check DB for unclosed orders and add it to trading context
        # closing_orders = self.order_manager.get_closing_orders(asset.ticker_symbol, price)
        ...

    def print_context(self) -> None:
        for asset in self.assets:
            try:
                trading_context = self.trading_context_manager.get_trading_context(asset.key)
                trading_context.end_time = time.time()
                market_data = self._fetch_market_data(asset)

                print("Trading Context")
                print(f"======= {asset.ticker_symbol} =======================")
                print(["Portfolio value", PortfolioHelper.calculate_portfolio_value(trading_context.available_balance,
                                                                                    market_data.close_price,
                                                                                    trading_context.open_positions)
                       ])
                print(["Unrealized PNL value", PortfolioHelper.calculate_unrealized_pnl_value(
                    trading_context.starting_balance, market_data.close_price,
                    trading_context.open_positions, trading_context.close_positions
                )
                       ])
                print(["self.start_time", trading_context.start_time])
                print(["self.starting_balance", trading_context.starting_balance])
                print(["self.available_balance", trading_context.available_balance])
                print(["self.closing_balance", trading_context.closing_balance])
                print(["self.buy_count", trading_context.buy_count])
                print(["self.lowest_buy", trading_context.lowest_buy])
                print(["self.highest_buy", trading_context.highest_buy])
                print(["self.lowest_sell", trading_context.lowest_sell])
                print(["self.highest_sell", trading_context.highest_sell])
                print(["self.open_positions", trading_context.open_positions])
                print(["self.close_positions", trading_context.close_positions])
                print(["self.end_time", trading_context.end_time])
                print(["self.last_activity_time", trading_context.last_activity_time])
            except Exception as exc:
                print(exc)
