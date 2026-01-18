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
    def __init__(self):
        self.current_session: Optional[TradingSession] = None
        self.is_running: Event = Event()
        self._lock = threading.Lock()

    def create_session(self, session_id: str) -> SessionManager:
        with self._lock:
            if self.is_running.is_set():
                raise ValueError("A session is already running. End it before creating a new one.")

            session = TradingSession(
                session_id=session_id,
                session_time=SessionTime(),
                trading_contexts={},
            )
            self.current_session = session
            return self

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
                exchange=asset.exchange.value
            )
            self.current_session.trading_contexts[asset.key] = ctx

    def get_trading_context(self, asset_key: int) -> TradingContext:
        with self._lock:
            return self.current_session.trading_contexts[asset_key]

    def update_available_balance(self, asset_key: int, available_balance: Decimal) -> None:
        with self._lock:
            self.current_session.trading_contexts[asset_key].available_balance = available_balance

    def record_position(self, asset_id: int, market_data: MarketData, trade_action: TradeAction) -> None:
        with self._lock:
            if not self.current_session:
                raise ValueError("No active session to record buy.")

            if asset_id not in self.current_session.trading_contexts:
                raise ValueError(f"Asset {asset_id} not initialized. Call init_asset first.")

            ctx = self.current_session.trading_contexts[asset_id]
            ctx.last_market_activity_time = market_data.timestamp

            if trade_action == TradeAction.BUY:
                self._record_buy_position(ctx, market_data)
            elif trade_action == TradeAction.SELL:
                self._record_sell_position(ctx, market_data)

    @staticmethod
    def _record_buy_position(context: TradingContext, market_data: MarketData) -> None:
        context.lowest_buy = min(context.lowest_buy, market_data.close_price)
        context.highest_buy = max(context.highest_buy, market_data.close_price)
        context.open_positions.append(market_data)

    @staticmethod
    def _record_sell_position(context: TradingContext, market_data: MarketData) -> None:
        context.lowest_sell = min(context.lowest_sell, market_data.close_price)
        context.highest_sell = max(context.highest_sell, market_data.close_price)
        context.close_positions.append(market_data)

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
            'is_running': self.is_running.is_set(),
            'duration': session.session_time.duration,
            'assets': len(session.trading_contexts),
            'contexts': {
                asset_id: {
                    'ticker_symbol': ctx.ticker_symbol,
                    'exchange': ctx.exchange,
                    'starting_balance': ctx.starting_balance,
                    'available_balance': ctx.available_balance,
                    'closing_balance': ctx.closing_balance,
                    'buy_count': ctx.buy_count,
                    'lowest_buy': ctx.lowest_buy if ctx.lowest_buy != float('inf') else None,
                    'highest_buy': ctx.highest_buy if ctx.highest_buy != float('-inf') else None,
                    'lowest_sell': ctx.lowest_sell if ctx.lowest_sell != float('inf') else None,
                    'highest_sell': ctx.highest_sell if ctx.highest_sell != float('-inf') else None,
                }
                for asset_id, ctx in session.trading_contexts.items()
            }
        }
