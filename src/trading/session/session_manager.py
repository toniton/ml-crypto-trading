from __future__ import annotations

import threading
import time
from decimal import Decimal
from threading import Event
from typing import Optional

from api.interfaces.asset import Asset
from api.interfaces.market_data import MarketData
from api.interfaces.session_time import SessionTime
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from api.interfaces.trading_session import TradingSession


class SessionManager:
    def __init__(self, config_vcs=None):
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
                raise ValueError(f"Asset {asset.key} already initialized.")

            ctx = TradingContext(
                starting_balance=starting_balance, ticker_symbol=asset.ticker_symbol,
                exchange=asset.exchange.value, commit_hash=self.current_session.commit_hash
            )
            self.current_session.trading_contexts[asset.key] = ctx

    def get_trading_context(self, asset_key: int) -> TradingContext:
        with self._lock:
            return self.current_session.trading_contexts[asset_key]

    def update_available_balance(self, asset_key: int, available_balance: Decimal) -> None:
        with self._lock:
            self.current_session.trading_contexts[asset_key].available_balance = available_balance

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
        context.open_positions.append(market_data)

        if quantity > 0:
            total_cost = (context.position_qty * context.avg_entry_price) + (quantity * price)
            context.position_qty += quantity
            context.avg_entry_price = total_cost / context.position_qty

    @staticmethod
    def _record_sell_position(context: TradingContext, market_data: MarketData,
                              quantity: Decimal, price: Decimal) -> None:
        context.lowest_sell = min(context.lowest_sell, market_data.close_price)
        context.highest_sell = max(context.highest_sell, market_data.close_price)
        context.close_positions.append(market_data)

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
