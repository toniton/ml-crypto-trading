from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, List, Optional

from src.configuration.trading_config import TradingConfig
from src.core.interfaces.trading_engine_proxy import (
    AssetRuntimeSnapshot,
    EngineStatus,
    RecordedMarketDataSummary,
    TradingEngineProxy,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.recorder.market_data_store import MarketDataStore
from src.trading.health.enums import TradingHealthState
from src.trading.managers.manager_container import ManagerContainer
from src.trading.trading_engine import TradingEngine


class LocalTradingEngineProxy(TradingEngineProxy, ApplicationLoggingMixin):
    """In-process proxy mediating API interactions with TradingEngine and related managers."""

    def __init__(
            self,
            trading_engine: TradingEngine,
            market_data_store: MarketDataStore,
            compare_backtest: Callable[[Any], Any],
    ) -> None:
        self._trading_engine = trading_engine
        self._market_data_store = market_data_store
        self._compare_backtest = compare_backtest
        self._applied_commit_hash: Optional[str] = None
        self._desired_commit_hash: Optional[str] = None
        self._sync_error: Optional[str] = None

    @property
    def _managers(self) -> Optional[ManagerContainer]:
        if self._trading_engine is not None:
            return self._trading_engine.managers
        return None

    def set_applied_commit_hash(self, commit_hash: str) -> None:
        self._applied_commit_hash = commit_hash
        self._desired_commit_hash = commit_hash
        self._sync_error = None

    def record_sync_error(self, desired_commit_hash: str, error_message: str) -> None:
        self._desired_commit_hash = desired_commit_hash
        self._sync_error = error_message

    def get_status(self) -> EngineStatus:
        is_running = self._trading_engine.is_running
        monitored_assets = self.list_monitored_assets()
        state = "RUNNING" if is_running else "STOPPED"
        applied_hash = self._applied_commit_hash
        if applied_hash is None and self._managers and self._managers.session_manager:
            raw_hash = self._managers.session_manager.get_current_commit_hash()
            if isinstance(raw_hash, str):
                applied_hash = raw_hash

        return EngineStatus(
            is_running=is_running,
            state=state,
            monitored_assets=monitored_assets,
            asset_count=len(monitored_assets),
            applied_commit_hash=applied_hash,
            desired_commit_hash=self._desired_commit_hash or applied_hash,
            sync_error=self._sync_error,
        )

    def list_monitored_assets(self) -> List[str]:
        return sorted([asset.ticker_symbol for asset in self._trading_engine.monitored_assets])

    def _find_monitored_asset(self, ticker_symbol: str) -> Optional[Any]:
        for asset in self._trading_engine.monitored_assets:
            if asset.ticker_symbol == ticker_symbol:
                return asset
        return None

    def _resolve_exchange(self, asset: Optional[Any], context: Optional[Any]) -> Optional[str]:
        if asset is not None and hasattr(asset, "exchange"):
            raw_exchange = getattr(asset.exchange, "value", asset.exchange)
            if isinstance(raw_exchange, str) and raw_exchange:
                return raw_exchange
        if context is not None:
            ctx_exchange = getattr(context, "exchange", None)
            if isinstance(ctx_exchange, str) and ctx_exchange:
                return ctx_exchange
        return None

    def _fetch_open_orders_count(self, exchange: Optional[str], ticker_symbol: str) -> int:
        if exchange:
            try:
                open_orders = self._managers.order_manager.get_open_orders(exchange, ticker_symbol)
                return len(open_orders) if open_orders else 0
            except Exception:  # pylint: disable=broad-except
                return 0
        return 0

    def _resolve_latest_price(self, ticker_symbol: str, asset: Optional[Any]) -> Optional[float]:
        try:
            price = self._managers.market_data_manager.get_last_price(ticker_symbol)
            if isinstance(price, (int, float, Decimal)) and float(price) > 0:
                return float(price)
        except Exception:  # pylint: disable=broad-except
            pass
        if asset is not None:
            try:
                market_data = self._managers.market_data_manager.get_market_data(asset)
                close_price = getattr(market_data, "close_price", None)
                if isinstance(close_price, (int, float, Decimal)) and float(close_price) > 0:
                    return float(close_price)
            except Exception:  # pylint: disable=broad-except
                pass
        return None

    def _resolve_balances_and_position(
            self,
            asset: Optional[Any],
            exchange: Optional[str],
            context: Optional[Any],
    ) -> tuple[float, int, Optional[float], Optional[float]]:
        position_quantity = 0.0
        total_trades_count = 0
        starting_balance: Optional[float] = None
        available_balance: Optional[float] = None
        if context is not None:
            raw_pos = getattr(context, "position_qty", 0.0)
            if isinstance(raw_pos, (int, float, Decimal)):
                position_quantity = float(raw_pos)
            raw_trades = getattr(context, "trades", None)
            total_trades_count = len(raw_trades) if raw_trades is not None else 0
            raw_starting = getattr(context, "starting_balance", None)
            if isinstance(raw_starting, (int, float, Decimal)):
                starting_balance = float(raw_starting)
            raw_available = getattr(context, "available_balance", None)
            if isinstance(raw_available, (int, float, Decimal)):
                available_balance = float(raw_available)

        if asset is not None and exchange is not None and self._managers.account_manager is not None:
            if available_balance is None or available_balance <= 0.0:
                available_balance = self._fetch_quote_balance(asset, exchange, available_balance)
            if position_quantity <= 0.0:
                position_quantity = self._fetch_base_balance(asset, exchange, position_quantity)

        return position_quantity, total_trades_count, starting_balance, available_balance

    def _fetch_quote_balance(
            self, asset: Any, exchange: str, fallback: Optional[float]
    ) -> Optional[float]:
        try:
            quote_bal = self._managers.account_manager.get_quote_balance(asset, exchange)
            raw_quote = getattr(quote_bal, "available_balance", None)
            if isinstance(raw_quote, (int, float, Decimal)) and float(raw_quote) >= 0.0:
                return float(raw_quote)
        except Exception:  # pylint: disable=broad-except
            pass
        return fallback

    def _fetch_base_balance(self, asset: Any, exchange: str, fallback: float) -> float:
        try:
            base_bal = self._managers.account_manager.get_base_balance(asset, exchange)
            raw_base = getattr(base_bal, "available_balance", None)
            if isinstance(raw_base, (int, float, Decimal)) and float(raw_base) > 0.0:
                return float(raw_base)
        except Exception:  # pylint: disable=broad-except
            pass
        return fallback

    def get_asset_snapshot(self, ticker_symbol: str) -> Optional[AssetRuntimeSnapshot]:
        asset = self._find_monitored_asset(ticker_symbol)
        if asset is None and not self._has_asset(ticker_symbol):
            return None

        context = self._managers.session_manager.get_trading_context_by_symbol(ticker_symbol)
        exchange = self._resolve_exchange(asset, context)
        open_orders_count = self._fetch_open_orders_count(exchange, ticker_symbol)
        latest_price = self._resolve_latest_price(ticker_symbol, asset)
        (
            position_quantity,
            total_trades_count,
            starting_balance,
            available_balance,
        ) = self._resolve_balances_and_position(asset, exchange, context)

        active_strategies = [
            strat.name
            for strat in self._trading_engine.strategies
            if strat.ticker_symbols is None or ticker_symbol in strat.ticker_symbols
        ]

        return AssetRuntimeSnapshot(
            ticker_symbol=ticker_symbol,
            active_strategies=active_strategies,
            open_orders_count=open_orders_count,
            total_trades_count=total_trades_count,
            position_quantity=position_quantity,
            latest_price=latest_price,
            starting_balance=starting_balance,
            available_balance=available_balance,
        )

    def _has_asset(self, ticker_symbol: str) -> bool:
        return self._managers.session_manager.has_session(ticker_symbol)

    def get_recorded_market_data(self) -> List[RecordedMarketDataSummary]:
        results: List[RecordedMarketDataSummary] = []
        for ticker in self._market_data_store.tickers():
            obs = self._market_data_store.observations(ticker)
            if obs:
                start_ts = datetime.fromtimestamp(int(obs[0].timestamp), tz=timezone.utc).isoformat()
                end_ts = datetime.fromtimestamp(int(obs[-1].timestamp), tz=timezone.utc).isoformat()
                results.append(
                    RecordedMarketDataSummary(
                        ticker_symbol=ticker,
                        observation_count=len(obs),
                        start_time=start_ts,
                        end_time=end_ts,
                    )
                )
        return results

    def get_market_data_store(self) -> MarketDataStore:
        return self._market_data_store

    def update_config(self, trading_config: TradingConfig) -> None:
        self._trading_engine.update_config(trading_config)

    def compare_backtest_drift(self, action: Any) -> Any:
        return self._compare_backtest(action)

    def _get_reconciliation_engine(self):
        if self._managers is not None:
            return self._managers.reconciliation_engine
        return None

    def get_reconciliation_status(self) -> dict[str, Any]:
        engine = self._get_reconciliation_engine()
        if not engine:
            return {"active": False, "has_critical": False, "discrepancies": []}
        active_discrepancies = engine.get_active_discrepancies()
        return {
            "active": True,
            "has_critical": engine.has_critical_discrepancy(),
            "discrepancies": [
                {
                    "type": str(d.discrepancy_type.value),
                    "severity": str(d.severity.value),
                    "exchange": d.exchange,
                    "asset_or_currency": d.asset_or_currency,
                    "local_value": str(d.local_value),
                    "exchange_value": str(d.exchange_value),
                    "difference": str(d.difference) if d.difference is not None else None,
                    "action_taken": d.action_taken,
                    "timestamp": d.timestamp,
                }
                for d in active_discrepancies
            ],
        }

    def trigger_reconciliation(self) -> bool:
        engine = self._get_reconciliation_engine()
        if engine:
            engine.trigger()
            return True
        return False

    def clear_reconciliation_discrepancies(self) -> bool:
        engine = self._get_reconciliation_engine()
        if engine:
            engine.clear_discrepancies()
            return True
        return False

    def _get_health_monitor(self):
        if self._managers is not None:
            return self._managers.health_monitor
        return None

    def get_health_snapshot(self) -> Optional[dict[str, Any]]:
        monitor = self._get_health_monitor()
        if not monitor:
            return None
        snapshot = monitor.snapshot
        return {
            "state": snapshot.state.value,
            "version": snapshot.version,
            "effective_permissions": [p.value for p in snapshot.effective_permissions],
            "active_conditions": [
                {
                    "condition": c.condition.value,
                    "scope_type": c.scope.scope_type.value,
                    "scope_identifier": c.scope.identifier,
                    "severity": c.severity.value,
                    "first_detected_at": c.first_detected_at.isoformat(),
                    "last_observed_at": c.last_observed_at.isoformat(),
                    "measured_value": str(c.measured_value) if c.measured_value is not None else None,
                    "threshold": str(c.threshold) if c.threshold is not None else None,
                    "consecutive_healthy_checks": c.consecutive_healthy_checks,
                }
                for c in snapshot.active_conditions
            ],
            "updated_at": snapshot.updated_at.isoformat(),
        }

    def pause_trading(self) -> Optional[dict[str, Any]]:
        monitor = self._get_health_monitor()
        if not monitor:
            return None
        monitor.set_state(TradingHealthState.PAUSED)
        return self.get_health_snapshot()

    def resume_trading(self) -> Optional[dict[str, Any]]:
        monitor = self._get_health_monitor()
        if not monitor:
            return None
        monitor.set_state(TradingHealthState.RECOVERING)
        return self.get_health_snapshot()
