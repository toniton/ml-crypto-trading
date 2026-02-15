from typing import List

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trading_context import TradingContext
from src.core.expressions.default_context import DefaultContext
from src.core.interfaces.expression_context import ExpressionContext


class TradingExpressionFactory:
    @staticmethod
    def create_context(
            asset: Asset,
            market_data: MarketData,
            account_balance: AccountBalance,
            trading_context: TradingContext,
            consensus_score: float = 0.0,
            candles: List[Candle] = None
    ) -> ExpressionContext:
        candles = candles or []

        close = float(market_data.close_price)
        high = float(market_data.high_price)
        low = float(market_data.low_price)
        volume = float(market_data.volume)
        range_val = high - low

        available_balance = float(account_balance.available_balance)
        position_qty = float(trading_context.position_qty)
        avg_entry = float(trading_context.avg_entry_price)
        equity = available_balance + (position_qty * close)
        pnl = (close - avg_entry) * position_qty if position_qty > 0 else 0.0

        variables = {
            # Market
            "close": close,
            "high": high,
            "low": low,
            "volume": volume,
            "range": range_val,
            "range_pct": range_val / close if close > 0 else 0.0,

            # Account
            "balance": available_balance,
            "equity": equity,

            # Risk
            "risk_pct": 0.01,  # Default, could be moved to config

            # Signal
            "signal": consensus_score,

            # Position
            "position_qty": position_qty,
            "avg_entry": avg_entry,
            "pnl": pnl,
            "exit_qty": float(trading_context.exit_qty),
            "avg_exit_price": float(trading_context.avg_exit_price),
            "realized_pnl": float(trading_context.realized_pnl),

            # Static
            "min_qty": float(asset.min_quantity),
            "decimals": asset.decimal_places,

            # Helpers
            "candles": candles
        }

        functions = {
            "max": max,
            "min": min,
            "avg": lambda *args: sum(args) / len(args) if args else 0.0,
            "sma": lambda n: sum([float(c.close) for c in candles[-n:]]) / n if candles and len(candles) >= n else 0.0,
            "ema": TradingExpressionFactory._calculate_ema(candles),
            "rsi": TradingExpressionFactory._calculate_rsi(candles)
        }

        return DefaultContext(variables=variables, functions=functions)

    @staticmethod
    def _calculate_ema(candles: List[Candle]):
        def ema(n):
            if not candles or len(candles) < n:
                return 0.0
            prices = [float(c.close) for c in candles[-n:]]
            multiplier = 2 / (n + 1)
            ema_val = sum(prices[:n]) / n
            for price in prices[n:]:
                ema_val = (price - ema_val) * multiplier + ema_val
            return ema_val

        return ema

    @staticmethod
    def _calculate_rsi(candles: List[Candle]):
        def rsi(n):
            if not candles or len(candles) <= n:
                return 50.0
            prices = [float(c.close) for c in candles[-(n + 1):]]
            deltas = [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]
            gains = [d for d in deltas if d > 0]
            losses = [-d for d in deltas if d < 0]

            avg_gain = sum(gains) / n
            avg_loss = sum(losses) / n

            if avg_loss == 0:
                return 100.0
            rs = avg_gain / avg_loss
            return 100.0 - (100.0 / (1 + rs))

        return rsi
