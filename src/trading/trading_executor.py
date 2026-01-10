from __future__ import annotations

import uuid
from queue import Queue

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_session import TradingSession
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.core.logging.trading_logging_mixin import TradingLoggingMixin
from src.core.logging.audit_logging_mixin import AuditLoggingMixin
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
        self.session_manager = manager_container.session_manager
        self.protection_manager = manager_container.protection_manager
        self.activity_queue = activity_queue

    def init_application(self):
        self.session_manager.create_session(session_id=str(uuid.uuid4())).start_session()
        self.account_manager.init_account_balances(self.session_manager)
        self.fees_manager.init_account_fees()
        self.account_manager.init_websocket()
        self.order_manager.initialize(self.assets)
        self.market_data_manager.init_websocket()

    def _should_trade(self, asset: Asset, action: TradeAction, market_data: MarketData, candles: list[Candle]) -> bool:
        trading_context = self.session_manager.get_trading_context(asset.key)

        if not self.protection_manager.can_trade(asset.key, action, trading_context, market_data):
            return False

        consensus_result = self.consensus_manager.get_quorum(
            action, asset.ticker_symbol, trading_context, market_data, candles
        )
        self.app_logger.debug(f"Consensus={consensus_result} for asset={asset}")
        return bool(consensus_result)

    def _prepare_trade_context(self, asset: Asset) -> tuple[AccountBalance, MarketData, list[Candle], Fees]:
        account_balance = self.account_manager.get_balance(asset, asset.exchange.value)
        if account_balance.available_balance <= 0:
            self.app_logger.debug(f"Balance too low for {asset}: {account_balance}")
            raise ValueError(f"Insufficient balance for {asset.quote_ticker_symbol}")

        market_data = self.market_data_manager.get_market_data(asset)
        self.app_logger.debug(f"Fetched market data for {asset}: {market_data}")
        fees = self.fees_manager.get_instrument_fees(asset.ticker_symbol, asset.exchange.value)
        candles = self.market_data_manager.get_candles(asset)

        return account_balance, market_data, candles, fees

    def create_buy_order(self, assets: list[Asset]):
        for asset in assets:
            try:
                account_balance, market_data, candles, fees = self._prepare_trade_context(asset)
                self.session_manager.update_available_balance(asset.key, account_balance.available_balance)
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
                self.session_manager.record_position(asset.key, market_data, TradeAction.BUY)

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
                trading_context = self.session_manager.get_trading_context(asset.key)
                if not trading_context.open_positions:
                    self.app_logger.debug(f"No open positions for {asset}")
                    continue
                _, market_data, candles, fees = self._prepare_trade_context(asset)
                current_price = market_data.close_price

                self.app_logger.debug(f"Current price for {asset}: {current_price}, Fees={fees}")

                if not self._should_trade(asset, TradeAction.SELL, market_data, candles):
                    continue

                open_positions: list[MarketData] = sorted(
                    trading_context.open_positions,
                    key=lambda o, _current_price=market_data.close_price:
                    (float(_current_price) - float(o.close_price)) / float(o.close_price)
                )

                quantity = format(asset.min_quantity, "f")
                best_position: MarketData | None = next(iter(open_positions), None)
                if best_position:
                    sell_order = self.order_manager.open_order(
                        price=current_price, trade_action=TradeAction.SELL,
                        quantity=quantity, provider_name=asset.exchange.value,
                        ticker_symbol=asset.ticker_symbol, timestamp=market_data.timestamp
                    )
                    self.activity_queue.put_nowait(sell_order.model_dump_json())
                    self.session_manager.record_position(asset.key, market_data, TradeAction.SELL)

                    self.trading_logger.info(
                        f"Order closed: {asset.ticker_symbol} SELL {quantity} @ {current_price}")

                    self.log_audit_event(
                        event_type='order_closed',
                        asset=asset.ticker_symbol,
                        action=TradeAction.SELL.value,
                        market_data=market_data,
                        context=f'order_id={sell_order.uuid},price={current_price},quantity={quantity}'
                    )

            except Exception as exc:
                self.app_logger.error(f"Error finalizing asset {asset}: {exc}", exc_info=True)
        self.app_logger.debug("Check unclosed orders completed")

    def stop(self):
        self.order_manager.shutdown()
        self.account_manager.close_account_balances(self.session_manager)
        session = self.session_manager.end_session()
        self._print_session_summary(session)

    def _print_session_summary(self, session: TradingSession) -> None:
        session_summary = self.session_manager.get_session_summary(session)
        self.app_logger.info("Trading Context Summary")
        self.app_logger.info("==============================")
        self.app_logger.info(session_summary)
        self.app_logger.info("------------------------------")
