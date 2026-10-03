from __future__ import annotations

from datetime import datetime, timezone
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
from src.trading.managers.manager_container import ManagerContainer
from src.trading.trading_engine import TradingEngine


class LocalTradingEngineProxy(TradingEngineProxy, ApplicationLoggingMixin):
    """In-process proxy mediating API interactions with TradingEngine and related managers."""

    def __init__(
            self,
            trading_engine: TradingEngine,
            managers: ManagerContainer,
            market_data_store: MarketDataStore,
            compare_backtest: Callable[[Any], Any],
    ) -> None:
        self._trading_engine = trading_engine
        self._managers = managers
        self._market_data_store = market_data_store
        self._compare_backtest = compare_backtest

    def get_status(self) -> EngineStatus:
        is_running = self._trading_engine.is_running
        monitored_assets = self.list_monitored_assets()
        state = "RUNNING" if is_running else "STOPPED"

        return EngineStatus(
            is_running=is_running,
            state=state,
            monitored_assets=monitored_assets,
            asset_count=len(monitored_assets),
        )

    def list_monitored_assets(self) -> List[str]:
        return sorted([asset.ticker_symbol for asset in self._trading_engine.monitored_assets])

    def get_asset_snapshot(self, ticker_symbol: str) -> Optional[AssetRuntimeSnapshot]:
        monitored = self.list_monitored_assets()
        if ticker_symbol not in monitored and not self._has_asset(ticker_symbol):
            return None

        open_orders = self._managers.order_manager.get_open_orders(ticker_symbol)
        open_orders_count = len(open_orders) if open_orders else 0

        price = self._managers.market_data_manager.get_last_price(ticker_symbol)
        latest_price = float(price) if price is not None else None

        position_quantity = 0.0
        total_trades_count = 0
        context = self._managers.session_manager.get_trading_context_by_symbol(ticker_symbol)
        if context is not None:
            position_quantity = float(context.position_qty)
            total_trades_count = len(context.trades)

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

    def get_reconciliation_status(self) -> dict[str, Any]:
        engine = getattr(self._trading_engine, "_reconciliation_engine", None)
        if not engine:
            return {"active": False, "has_critical": False, "discrepancies": []}
        active_discrepancies = engine.get_active_discrepancies()
        return {
            "active": True,
            "has_critical": engine.has_critical_discrepancy(),
            "discrepancies": [
                {
                    "type": d.discrepancy_type.value if hasattr(d.discrepancy_type, "value") else str(d.discrepancy_type),
                    "severity": d.severity.value if hasattr(d.severity, "value") else str(d.severity),
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
        engine = getattr(self._trading_engine, "_reconciliation_engine", None)
        if engine:
            engine.trigger()
            return True
        return False

    def clear_reconciliation_discrepancies(self) -> bool:
        engine = getattr(self._trading_engine, "_reconciliation_engine", None)
        if engine:
            engine.clear_discrepancies()
            return True
        return False

