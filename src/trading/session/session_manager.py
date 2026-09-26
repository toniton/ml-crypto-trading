from __future__ import annotations

import threading
import time
from decimal import Decimal
from threading import Event
from typing import Optional

from api.interfaces.asset import Asset
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.position_entry import PositionEntry
from api.interfaces.position_lot import PositionLot
from api.interfaces.session_time import SessionTime
from api.interfaces.trade import Trade
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from api.interfaces.trading_session import TradingSession
from src.vcs.application import VCSService


class SessionManager:
    def __init__(self, config_vcs: VCSService = None):
        self.current_session: Optional[TradingSession] = None
        self.is_running: Event = Event()
        self._lock = threading.Lock()
        self._config_vcs = config_vcs

    def create_session(self, session_id: str, commit_hash: Optional[str] = None) -> SessionManager:
        with self._lock:
            if self.is_running.is_set():
                raise ValueError("A session is already running. End it before creating a new one.")

            if commit_hash is None and self._config_vcs is not None:
                commit_hash = self._fetch_head_commit_hash()

            session = TradingSession(
                session_id=session_id,
                session_time=SessionTime(),
                trading_contexts={},
                commit_hash=commit_hash,
            )
            self.current_session = session
            return self

    def _fetch_head_commit_hash(self) -> Optional[str]:
        try:
            return self._config_vcs.head("HEAD").hash
        except Exception:  # pylint: disable=broad-except
            return None

    def get_current_commit_hash(self) -> str:
        with self._lock:
            if self.current_session and self.current_session.commit_hash:
                return self.current_session.commit_hash
        fetched = self._fetch_head_commit_hash()
        return fetched or "HEAD"

    def update_commit_hash(self, commit_hash: str) -> None:
        with self._lock:
            if self.current_session:
                self.current_session.commit_hash = commit_hash

    def start_session(self) -> None:
        with self._lock:
            if not self.current_session:
                raise ValueError("No session created. Call create_session first.")

            self.current_session.session_time.start_time = time.time()
            self.is_running.set()

    def init_asset_balance(self, asset: Asset, starting_balance: Decimal) -> None:
        with self._lock:
            if not self.current_session:
                raise ValueError("No active session.")

            if asset.key in self.current_session.trading_contexts:
                return

            ctx = TradingContext(
                starting_balance=starting_balance, ticker_symbol=asset.ticker_symbol,
                exchange=asset.exchange.value, commit_hash=self.current_session.commit_hash
            )
            self.current_session.trading_contexts[asset.key] = ctx

    def get_trading_context(self, asset_key: int) -> Optional[TradingContext]:
        with self._lock:
            if not self.current_session:
                return None
            return self.current_session.trading_contexts.get(asset_key)

    def get_trading_context_by_symbol(self, ticker_symbol: str) -> Optional[TradingContext]:
        with self._lock:
            if not self.current_session:
                return None
            for ctx in self.current_session.trading_contexts.values():
                if ctx.ticker_symbol == ticker_symbol:
                    return ctx
            return None

    def update_available_balance(self, asset_key: int, available_balance: Decimal) -> None:
        with self._lock:
            if not self.current_session:
                return
            ctx = self.current_session.trading_contexts.get(asset_key)
            if ctx is not None:
                ctx.available_balance = available_balance

    def record_order_fill(self, order: Order) -> list[Trade]:
        with self._lock:
            if not self.current_session:
                return []

            ctx = self._find_context(order.ticker_symbol)
            if ctx is None:
                return []

            fill_price = (
                order.fill_price
                if (order.fill_price is not None and order.fill_price > Decimal(0))
                else order.price
            )
            quantity = Decimal(str(order.quantity))
            fee = order.fees if order.fees is not None else Decimal(0)
            timestamp = float(
                order.executed_time
                if order.executed_time is not None
                else order.created_time
            )
            ctx.last_market_activity_time = timestamp

            if order.trade_action == TradeAction.BUY:
                self._record_buy_fill(ctx, order, fill_price, quantity, fee, timestamp)
                return []

            if order.trade_action == TradeAction.SELL:
                return self._record_sell_fill(ctx, order, fill_price, quantity, fee, timestamp)

            return []

    def _find_context(self, ticker_symbol: str) -> Optional[TradingContext]:
        if not self.current_session:
            return None
        for ctx in self.current_session.trading_contexts.values():
            if ctx.ticker_symbol == ticker_symbol:
                return ctx
        return None

    def _record_buy_fill(
            self,
            ctx: TradingContext,
            order: Order,
            fill_price: Decimal,
            quantity: Decimal,
            fee: Decimal,
            timestamp: float,
    ) -> None:
        ctx.lowest_buy = min(ctx.lowest_buy, fill_price)
        ctx.highest_buy = max(ctx.highest_buy, fill_price)
        ctx.open_positions.append(PositionEntry(
            price=fill_price,
            quantity=quantity,
            timestamp=timestamp,
        ))
        lot = PositionLot.create(
            order_uuid=order.uuid,
            ticker_symbol=order.ticker_symbol,
            price=fill_price,
            quantity=quantity,
            fee=fee,
            timestamp=timestamp,
            winning_strategy=order.winning_strategy,
            strategy_votes=order.strategy_votes,
        )
        ctx.position_lots.append(lot)
        if quantity > Decimal(0):
            total_cost = (ctx.position_qty * ctx.avg_entry_price) + (quantity * fill_price)
            ctx.position_qty += quantity
            ctx.avg_entry_price = total_cost / ctx.position_qty

    def _record_sell_fill(
            self,
            ctx: TradingContext,
            order: Order,
            fill_price: Decimal,
            quantity: Decimal,
            fee: Decimal,
            timestamp: float,
    ) -> list[Trade]:
        ctx.lowest_sell = min(ctx.lowest_sell, fill_price)
        ctx.highest_sell = max(ctx.highest_sell, fill_price)
        ctx.close_positions.append(PositionEntry(
            price=fill_price,
            quantity=quantity,
            timestamp=timestamp,
        ))
        if quantity > Decimal(0):
            total_exit_value = (ctx.exit_qty * ctx.avg_exit_price) + (quantity * fill_price)
            ctx.exit_qty += quantity
            ctx.avg_exit_price = total_exit_value / ctx.exit_qty

        completed_trades = self._match_fifo_lots(ctx, order, fill_price, quantity, fee, timestamp)
        ctx.position_qty = max(Decimal(0), ctx.position_qty - quantity)
        if ctx.position_qty == Decimal(0):
            ctx.avg_entry_price = Decimal(0)
        return completed_trades

    def _match_fifo_lots(
            self,
            ctx: TradingContext,
            order: Order,
            fill_price: Decimal,
            quantity: Decimal,
            fee: Decimal,
            timestamp: float,
    ) -> list[Trade]:
        completed_trades: list[Trade] = []
        sell_remaining = quantity
        sell_fee_per_unit = (fee / quantity) if quantity > Decimal(0) else Decimal(0)

        while sell_remaining > Decimal(0) and ctx.position_lots:
            lot = ctx.position_lots[0]
            matched_qty = min(sell_remaining, lot.remaining_quantity)
            trade = self._match_single_lot(
                ctx=ctx,
                order=order,
                fill_price=fill_price,
                matched_qty=matched_qty,
                lot=lot,
                sell_fee_per_unit=sell_fee_per_unit,
                timestamp=timestamp,
            )
            completed_trades.append(trade)

            lot.remaining_quantity -= matched_qty
            sell_remaining -= matched_qty
            if lot.remaining_quantity <= Decimal(0):
                ctx.position_lots.pop(0)

        if sell_remaining > Decimal(0):
            fallback_gross = (fill_price - ctx.avg_entry_price) * sell_remaining
            fallback_exit_fee = sell_fee_per_unit * sell_remaining
            ctx.realized_pnl += (fallback_gross - fallback_exit_fee)

        return completed_trades

    def _match_single_lot(
            self,
            ctx: TradingContext,
            order: Order,
            fill_price: Decimal,
            matched_qty: Decimal,
            lot: PositionLot,
            sell_fee_per_unit: Decimal,
            timestamp: float,
    ) -> Trade:
        trade = Trade.create(
            ticker_symbol=order.ticker_symbol,
            entry_order_uuid=lot.order_uuid,
            exit_order_uuid=order.uuid,
            entry_price=lot.price,
            exit_price=fill_price,
            quantity=matched_qty,
            entry_fee=lot.fee_per_unit * matched_qty,
            exit_fee=sell_fee_per_unit * matched_qty,
            entry_timestamp=lot.timestamp,
            exit_timestamp=timestamp,
            commit_hash=order.commit_hash or ctx.commit_hash,
            winning_strategy=order.winning_strategy or lot.winning_strategy,
            strategy_votes=order.strategy_votes or lot.strategy_votes,
        )
        ctx.trades.append(trade)
        ctx.realized_pnl += trade.net_pnl
        return trade

    def record_position(self, asset_id: int, market_data: MarketData, trade_action: TradeAction,
                        quantity: Decimal = Decimal(0), price: Decimal = Decimal(0)) -> None:
        with self._lock:
            if not self.current_session:
                raise ValueError("No active session to record buy.")

            if asset_id not in self.current_session.trading_contexts:
                raise ValueError(f"Asset {asset_id} not initialized. Call init_asset first.")

            ctx = self.current_session.trading_contexts[asset_id]
            ctx.last_market_activity_time = market_data.timestamp

            if trade_action == TradeAction.BUY:
                self._record_buy_position(ctx, market_data, quantity, price)
            elif trade_action == TradeAction.SELL:
                self._record_sell_position(ctx, market_data, quantity, price)

    @staticmethod
    def _record_buy_position(context: TradingContext, market_data: MarketData,
                             quantity: Decimal, price: Decimal) -> None:
        context.lowest_buy = min(context.lowest_buy, market_data.close_price)
        context.highest_buy = max(context.highest_buy, market_data.close_price)
        pos_entry = PositionEntry(
            price=price if price > 0 else Decimal(str(market_data.close_price)),
            quantity=quantity if quantity > 0 else Decimal(str(market_data.volume)),
            timestamp=float(market_data.timestamp),
        )
        context.open_positions.append(pos_entry)

        if quantity > 0:
            total_cost = (context.position_qty * context.avg_entry_price) + (quantity * price)
            context.position_qty += quantity
            context.avg_entry_price = total_cost / context.position_qty

    @staticmethod
    def _record_sell_position(context: TradingContext, market_data: MarketData,
                              quantity: Decimal, price: Decimal) -> None:
        context.lowest_sell = min(context.lowest_sell, market_data.close_price)
        context.highest_sell = max(context.highest_sell, market_data.close_price)
        pos_entry = PositionEntry(
            price=price if price > 0 else Decimal(str(market_data.close_price)),
            quantity=quantity if quantity > 0 else Decimal(str(market_data.volume)),
            timestamp=float(market_data.timestamp),
        )
        context.close_positions.append(pos_entry)

        if quantity > 0:
            # Accumulate avg exit price
            total_exit_value = (context.exit_qty * context.avg_exit_price) + (quantity * price)
            context.exit_qty += quantity
            context.avg_exit_price = total_exit_value / context.exit_qty

            # Realized PnL
            realized = (price - context.avg_entry_price) * quantity
            context.realized_pnl += realized

            # Reduce open position
            context.position_qty = max(Decimal(0), context.position_qty - quantity)
            if context.position_qty == 0:
                context.avg_entry_price = Decimal(0)

    def get_unrealized_pnl(self, asset_id: int, current_price: Decimal) -> Decimal:
        with self._lock:
            ctx = self.current_session.trading_contexts[asset_id]
            if ctx.position_qty == 0:
                return Decimal(0)
            return (current_price - ctx.avg_entry_price) * ctx.position_qty

    def close_asset_balance(self, asset_id: int, closing_balance: Decimal) -> None:
        with self._lock:
            if not self.current_session:
                raise ValueError("No active session.")

            ctx = self.current_session.trading_contexts[asset_id]
            ctx.closing_balance = closing_balance

    def end_session(self) -> TradingSession:
        with self._lock:
            if not self.current_session:
                raise ValueError("No active session to end.")

            self.is_running.clear()
            self.current_session.session_time.end_time = time.time()

            completed_session = self.current_session
            self.current_session = None
            return completed_session

    def get_session_summary(self, session: TradingSession) -> dict:
        return {
            'session_id': session.session_id,
            'commit_hash': session.commit_hash,
            'is_running': self.is_running.is_set(),
            'duration': session.session_time.duration,
            'assets': len(session.trading_contexts),
            'contexts': {
                asset_id: {
                    'ticker_symbol': ctx.ticker_symbol,
                    'exchange': ctx.exchange,
                    'commit_hash': ctx.commit_hash,
                    'starting_balance': ctx.starting_balance,
                    'available_balance': ctx.available_balance,
                    'closing_balance': ctx.closing_balance,
                    'buy_count': ctx.buy_count,
                    'lowest_buy': ctx.lowest_buy if ctx.lowest_buy != Decimal('inf') else None,
                    'highest_buy': ctx.highest_buy if ctx.highest_buy != Decimal('-inf') else None,
                    'lowest_sell': ctx.lowest_sell if ctx.lowest_sell != Decimal('inf') else None,
                    'highest_sell': ctx.highest_sell if ctx.highest_sell != Decimal('-inf') else None,
                }
                for asset_id, ctx in session.trading_contexts.items()
            }
        }
