from typing import List, Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.core.expressions.default_context import DefaultContext
from src.core.expressions.rolling_window_evaluator import RollingWindowEvaluator
from src.core.interfaces.expression_context import ExpressionContext
from src.trading.consensus.consensus_decision import ConsensusDecision
from src.trading.protection.portfolio_policy_resolver import EffectivePortfolioConfig
from src.trading.protection.quote_portfolio_guard import PortfolioRiskMetrics
from src.trading.regimes.market_regime import MarketRegime
from src.trading.regimes.market_regime_detector import MarketRegimeDetector


class TradingExpressionFactory:
    _detector = MarketRegimeDetector()

    @staticmethod
    def create_context(
            asset: Asset,
            market_data: MarketData,
            account_balance: AccountBalance,
            trading_context: TradingContext,
            decision: Optional[ConsensusDecision],
            candles: List[Candle] = None,
            risk_metrics: Optional[PortfolioRiskMetrics] = None,
            effective_config: Optional[EffectivePortfolioConfig] = None,
    ) -> ExpressionContext:
        candles = candles or []

        close = float(market_data.close_price)
        available_balance = float(account_balance.available_balance)
        position_qty = float(trading_context.position_qty)

        variables = {
            **TradingExpressionFactory._build_market_variables(market_data),
            **TradingExpressionFactory._build_regime_variables(candles, market_data),
            **TradingExpressionFactory._build_portfolio_variables(risk_metrics, effective_config),

            # Account
            "balance": available_balance,
            "equity": available_balance + (position_qty * close),

            # Risk
            "risk_pct": 0.01,  # Default, could be moved to config

            # Signal (action-aware consensus for the decision being executed)
            **TradingExpressionFactory._build_consensus_variables(decision),

            **TradingExpressionFactory._build_position_variables(trading_context, close),

            # Static
            "min_qty": float(asset.min_quantity),
            "decimals": asset.quote_decimals,

            # Helpers
            "candles": candles
        }

        return DefaultContext(
            variables=variables,
            functions=TradingExpressionFactory._build_functions(candles, market_data)
        )

    @staticmethod
    def _build_consensus_variables(decision: Optional[ConsensusDecision]) -> dict:
        if decision is None:
            return {
                "signal": 0,
                "confidence": 0.0,
                "vote_ratio": 0.0,
                "weighted_vote_ratio": 0.0,
                "quorum_threshold": 0.0,
                "quorum_margin": 0.0,
            }

        direction = 1 if decision.trade_action == TradeAction.BUY else -1
        return {
            # Directional signal: +1 for BUY, -1 for SELL (separated from strength)
            "signal": direction,
            # Strength of consensus (0.0..1.0) — use for position sizing
            "confidence": decision.vote_ratio,
            "vote_ratio": decision.vote_ratio,
            "weighted_vote_ratio": decision.weighted_vote_ratio,
            "quorum_threshold": decision.quorum_threshold,
            "quorum_margin": decision.quorum_margin,
        }

    @staticmethod
    def create_strategy_context(
            trading_context: TradingContext,
            market_data: MarketData,
            candles: List[Candle] = None
    ) -> ExpressionContext:
        candles = candles or []

        close = float(market_data.close_price)
        variables = {
            **TradingExpressionFactory._build_market_variables(market_data),
            **TradingExpressionFactory._build_regime_variables(candles, market_data),
            **TradingExpressionFactory._build_position_variables(trading_context, close),
            "candles": candles
        }

        return DefaultContext(
            variables=variables,
            functions=TradingExpressionFactory._build_functions(candles, market_data)
        )

    @staticmethod
    def _build_regime_variables(candles: List[Candle], market_data: MarketData) -> dict:
        metrics = TradingExpressionFactory._detector.detect(candles, market_data)
        multiplier = MarketRegime.get_exposure_multiplier(metrics.regime)
        return {
            "regime": metrics.regime.value,
            "regime_multiplier": multiplier,
            "volatility": metrics.volatility,
            "trend_strength": metrics.trend_strength,
            "liquidity": metrics.liquidity,
            "spread": metrics.spread,
            "NORMAL": MarketRegime.NORMAL.value,
            "EXTREME": MarketRegime.EXTREME.value,
            "TRENDING_UP": MarketRegime.TRENDING_UP.value,
            "TRENDING_DOWN": MarketRegime.TRENDING_DOWN.value,
            "RANGING": MarketRegime.RANGING.value,
            "HIGH_VOLATILITY": MarketRegime.HIGH_VOLATILITY.value,
            "LOW_VOLATILITY": MarketRegime.LOW_VOLATILITY.value,
            "ILLIQUID": MarketRegime.ILLIQUID.value,
            "UNKNOWN": MarketRegime.UNKNOWN.value,
        }

    @staticmethod
    def _build_portfolio_variables(
            risk_metrics: Optional[PortfolioRiskMetrics] = None,
            effective_config: Optional[EffectivePortfolioConfig] = None,
    ) -> dict:
        total_equity = float(risk_metrics.total_equity) if risk_metrics else 0.0
        total_cash = float(risk_metrics.total_cash) if risk_metrics else 0.0
        available_cash = float(risk_metrics.available_cash) if risk_metrics else 0.0
        reserved_cash = float(risk_metrics.reserved_cash) if risk_metrics else 0.0
        invested_notional = float(risk_metrics.invested_notional) if risk_metrics else 0.0
        total_exposure = float(risk_metrics.total_exposure_pct) if risk_metrics else 0.0
        drawdown = float(risk_metrics.drawdown_pct) if risk_metrics else 0.0
        open_positions = risk_metrics.open_position_count if risk_metrics else 0

        max_total = (
            float(effective_config.effective_max_total)
            if effective_config and effective_config.effective_max_total is not None
            else 0.80
        )
        max_asset = (
            float(effective_config.effective_max_per_asset)
            if effective_config and effective_config.effective_max_per_asset is not None
            else 0.25
        )
        max_quote = (
            float(effective_config.exposure.max_per_quote)
            if effective_config and effective_config.exposure.max_per_quote is not None
            else 0.50
        )
        min_reserve = (
            float(effective_config.guard.min_quote_reserve)
            if effective_config
            else 0.10
        )

        return {
            "portfolio_equity": total_equity,
            "portfolio_cash": total_cash,
            "portfolio_available_cash": available_cash,
            "portfolio_reserved_cash": reserved_cash,
            "portfolio_invested_notional": invested_notional,
            "portfolio_exposure": total_exposure,
            "portfolio_drawdown": drawdown,
            "portfolio_open_positions": open_positions,
            "max_exposure": max_total,
            "max_asset_exposure": max_asset,
            "max_quote_exposure": max_quote,
            "min_quote_reserve": min_reserve,
        }

    @staticmethod
    def _build_market_variables(market_data: MarketData) -> dict:
        close = float(market_data.close_price)
        high = float(market_data.high_price)
        low = float(market_data.low_price)
        range_val = high - low

        return {
            "close": close,
            "high": high,
            "low": low,
            "volume": float(market_data.volume),
            "range": range_val,
            "range_pct": range_val / close if close > 0 else 0.0,
        }

    @staticmethod
    def _build_position_variables(trading_context: TradingContext, close: float) -> dict:
        position_qty = float(trading_context.position_qty)
        avg_entry = float(trading_context.avg_entry_price)
        pnl = (close - avg_entry) * position_qty if position_qty > 0 else 0.0

        return {
            "position_qty": position_qty,
            "avg_entry": avg_entry,
            "pnl": pnl,
            "exit_qty": float(trading_context.exit_qty),
            "avg_exit_price": float(trading_context.avg_exit_price),
            "realized_pnl": float(trading_context.realized_pnl),
        }

    @staticmethod
    def _build_functions(candles: List[Candle], market_data: Optional[MarketData] = None) -> dict:
        close = float(market_data.close_price) if market_data else 0.0
        rolling_evaluator = RollingWindowEvaluator(candles, market_data)
        return {
            "max": max,
            "min": min,
            "avg": lambda *args: sum(args) / len(args) if args else 0.0,
            "abs": abs,
            "clamp": lambda val, min_v, max_v: max(min_v, min(val, max_v)),
            "round": round,
            "sma": lambda n: sum(float(c.close) for c in candles[-n:]) / n if candles and len(candles) >= n else 0.0,
            "ema": TradingExpressionFactory._calculate_ema(candles),
            "rsi": TradingExpressionFactory._calculate_rsi(candles),
            "atr": TradingExpressionFactory._calculate_atr(candles),
            "highest": rolling_evaluator.highest,
            "lowest": rolling_evaluator.lowest,
            "regime": (
                lambda period=20: TradingExpressionFactory._detector.detect(candles, market_data, period).regime.value
            ),
            "volatility": (
                lambda period=20: TradingExpressionFactory._detector.calculate_volatility(candles, close, period)
            ),
            "trend_strength": (
                lambda period=20: TradingExpressionFactory._detector.calculate_trend_strength(candles, period)
            ),
            "liquidity": (
                lambda period=20: TradingExpressionFactory._detector.calculate_liquidity(candles, market_data, period)
            ),
            "spread": lambda: TradingExpressionFactory._detector.calculate_spread(market_data, close),
        }

    @staticmethod
    def _calculate_ema(candles: List[Candle]):
        def ema(n):
            if n <= 0:
                raise ValueError("EMA period must be > 0")
            if not candles or len(candles) < n:
                return 0.0
            prices = [float(c.close) for c in candles]
            multiplier = 2 / (n + 1)
            ema_value = sum(prices[:n]) / n
            for price in prices[n:]:
                ema_value = (price - ema_value) * multiplier + ema_value
            return ema_value

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

    @staticmethod
    def _calculate_atr(candles: List[Candle]):
        def atr(n):
            if n <= 0:
                raise ValueError("ATR period must be > 0")
            if not candles or len(candles) <= 1:
                return 0.0

            true_ranges = []
            for i in range(1, len(candles)):
                curr = candles[i]
                prev = candles[i - 1]
                high = float(curr.high)
                low = float(curr.low)
                prev_close = float(prev.close)
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                true_ranges.append(tr)

            if not true_ranges:
                return 0.0

            window = true_ranges[-n:]
            return sum(window) / len(window)

        return atr
