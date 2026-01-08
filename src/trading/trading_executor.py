from __future__ import annotations

import time
from queue import Queue

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.core.logging.trading_logging_mixin import TradingLoggingMixin
from src.core.logging.audit_logging_mixin import AuditLoggingMixin
from src.trading.helpers.portfolio_helper import PortfolioHelper
from src.core.managers.manager_container import ManagerContainer


class TradingExecutor(ApplicationLoggingMixin, TradingLoggingMixin, AuditLoggingMixin):

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

    def _should_trade(self, asset: Asset, action: TradeAction, market_data: MarketData, candles: list[Candle]) -> bool:
        trading_context = self.trading_context_manager.get_trading_context(asset.key)

        if not self.protection_manager.can_trade(asset.key, action, trading_context, market_data):
            return False

        consensus_result = self.consensus_manager.get_quorum(
            action, asset.ticker_symbol, trading_context, market_data, candles
        )
        self.app_logger.debug(f"Consensus={consensus_result} for asset={asset}")
        return bool(consensus_result)

    def _prepare_trade_context(self, asset: Asset) -> tuple[AccountBalance, MarketData, list[Candle], Fees]:
        currency_symbol = asset.quote_ticker_symbol
        account_balance = self.account_manager.get_balance(currency_symbol, asset.exchange.value)
        if account_balance.available_balance <= 0:
            raise ValueError(f"Insufficient balance for {currency_symbol}: ${account_balance.available_balance}")

        market_data = self.market_data_manager.get_market_data(asset)
        self.app_logger.debug(f"Fetched market data for {asset}: {market_data}")
        fees = self.fees_manager.get_instrument_fees(asset.ticker_symbol, asset.exchange.value)
        candles = self.market_data_manager.get_candles(asset)

        return account_balance, market_data, candles, fees

    def create_buy_order(self, assets: list[Asset]):
        for asset in assets:
            try:
                account_balance, market_data, candles, fees = self._prepare_trade_context(asset)
                self.trading_context_manager.update_trading_context(asset.key, account_balance.available_balance)
                if not self._should_trade(asset, TradeAction.BUY, market_data, candles):
                    self.app_logger.debug(f"No consensus to buy {asset.ticker_symbol}")
                    continue

                self.app_logger.info(f"Consensus reached to buy {asset.ticker_symbol}")
                price = market_data.close_price
                price = float(price) + (float(price) * fees.maker_fee_pct * 0.01)
                price = format(round(price, asset.decimal_places), f".{asset.decimal_places}f")

                self.app_logger.debug([
                    f"Calculated price for {asset}: Price={price}",
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

                self.trading_logger.info(f"Order opened: {asset.ticker_symbol} BUY {quantity} @ {price}")

                self.log_audit_event(
                    event_type='order_opened',
                    asset=asset.ticker_symbol,
                    action=TradeAction.BUY.value,
                    market_data=market_data,
                    context=f'order_id={buy_order.uuid},price={price},quantity={quantity}'
                )
            except Exception as exc:
                self.app_logger.error(f"Error processing asset {asset}: {exc}", exc_info=True)

    def create_sell_order(self, assets: list[Asset]):
        for asset in assets:
            try:
                trading_context = self.trading_context_manager.get_trading_context(asset.key)
                if not trading_context.open_positions:
                    self.app_logger.debug(f"No open positions for {asset}")
                    continue
                _, market_data, candles, fees = self._prepare_trade_context(asset)
                current_price = market_data.close_price

                self.app_logger.debug(f"Current price for {asset}: {current_price}, Fees={fees}")

                if not self._should_trade(asset, TradeAction.SELL, market_data, candles):
                    continue

                open_orders: list[Order] = sorted(
                    trading_context.open_positions,
                    key=lambda o, _current_price=market_data.close_price:
                    (float(_current_price) - float(o.price)) / float(o.price)
                )

                best_order: Order | None = next(iter(open_orders), None)
                if best_order:
                    sell_order = self.order_manager.open_order(
                        price=current_price, trade_action=TradeAction.SELL,
                        quantity=best_order.quantity, provider_name=best_order.provider_name,
                        ticker_symbol=best_order.ticker_symbol, timestamp=market_data.timestamp
                    )
                    self.activity_queue.put_nowait(sell_order.model_dump_json())
                    self.trading_context_manager.record_sell(asset.key, sell_order)

                    self.trading_logger.info(
                        f"Order closed: {asset.ticker_symbol} SELL {best_order.quantity} @ {current_price}")

                    self.log_audit_event(
                        event_type='order_closed',
                        asset=asset.ticker_symbol,
                        action=TradeAction.SELL.value,
                        market_data=market_data,
                        context=f'order_id={sell_order.uuid},price={current_price},quantity={best_order.quantity}'
                    )

            except Exception as exc:
                self.app_logger.error(f"Error finalizing asset {asset}: {exc}", exc_info=True)
        self.app_logger.debug("Check unclosed orders completed")

    def stop(self):
        self.order_manager.stop_order_executions()
        self.order_manager.close_open_orders()

    def print_context(self) -> None:
        for asset in self.assets:
            try:
                trading_context = self.trading_context_manager.get_trading_context(asset.key)
                trading_context.end_time = time.time()
                market_data = self.market_data_manager.get_market_data(asset)

                self.app_logger.info("Trading Context Summary")
                self.app_logger.info(f"======= {asset.ticker_symbol} =======================")
                self.app_logger.info(
                    ["Portfolio value", PortfolioHelper.calculate_portfolio_value(trading_context.available_balance,
                                                                                  market_data.close_price,
                                                                                  trading_context.open_positions)
                     ])
                self.app_logger.info(["Unrealized PNL value", PortfolioHelper.calculate_unrealized_pnl_value(
                    trading_context.starting_balance, market_data.close_price,
                    trading_context.open_positions, trading_context.close_positions
                )
                                      ])
                self.app_logger.info(["self.start_time", trading_context.start_time])
                self.app_logger.info(["self.starting_balance", trading_context.starting_balance])
                self.app_logger.info(["self.available_balance", trading_context.available_balance])
                self.app_logger.info(["self.closing_balance", trading_context.closing_balance])
                self.app_logger.info(["self.buy_count", trading_context.buy_count])
                self.app_logger.info(["self.lowest_buy", trading_context.lowest_buy])
                self.app_logger.info(["self.highest_buy", trading_context.highest_buy])
                self.app_logger.info(["self.lowest_sell", trading_context.lowest_sell])
                self.app_logger.info(["self.highest_sell", trading_context.highest_sell])
                self.app_logger.info(["self.open_positions", trading_context.open_positions])
                self.app_logger.info(["self.close_positions", trading_context.close_positions])
                self.app_logger.info(["self.end_time", trading_context.end_time])
                self.app_logger.info(["self.last_activity_time", trading_context.last_activity_time])
            except Exception as exc:
                self.app_logger.error(f"Error printing context for {asset}: {exc}", exc_info=True)
