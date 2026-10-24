from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
    ExecutionConfiguration,
)
from src.backtest.domain.metrics import BacktestMetrics
from src.backtest.domain.result import BacktestResult
from src.backtest.domain.session import BacktestSession
from src.core.interfaces.execution_status import ExecutionStatus
from src.database.dao.backtest_result_dao import BacktestResultDao
from src.database.dao.backtest_session_dao import BacktestSessionDao
from src.trading.analytics.trade_attribution_service import (
    AttributionMetrics,
    TradeAttributionService,
)


class BacktestDBVSEntityMapper:

    @staticmethod
    def session_to_dao(session: BacktestSession) -> BacktestSessionDao:
        status_str = session.status.value
        config_dict: dict[str, Any] = {}
        if session.request:
            config_dict = {
                "start_time": session.request.start_time.isoformat() if session.request.start_time else None,
                "end_time": session.request.end_time.isoformat() if session.request.end_time else None,
                "initial_balance": str(session.request.initial_balance),
                "data_source": {
                    "source_type": (
                        session.request.data_source.source_type.value
                        if session.request.data_source
                        else "csv"
                    ),
                    "path": session.request.data_source.path if session.request.data_source else None,
                    "source_id": session.request.data_source.source_id if session.request.data_source else None,
                } if session.request.data_source else None,
                "execution": {
                    "latency_ms": session.request.execution.latency_ms,
                    "slippage_ticks": session.request.execution.slippage_ticks,
                    "fee_rate": str(session.request.execution.fee_rate),
                } if session.request.execution else None,
            }

        return BacktestSessionDao(
            id=session.id,
            ticker_symbol=session.ticker_symbol,
            status=status_str,
            config=config_dict,
            worker_id=session.worker_id,
            started_at=session.started_at,
            completed_at=session.completed_at,
            heartbeat_at=session.heartbeat_at,
            lease_expires_at=session.lease_expires_at,
            error_message=session.error,
            created_at=session.created_at,
            updated_at=session.completed_at or session.started_at or session.created_at,
        )

    @staticmethod
    def dao_to_session(dao: BacktestSessionDao) -> BacktestSession:
        config = dao.config or {}
        start_time = None
        if config.get("start_time"):
            start_time = datetime.fromisoformat(config["start_time"])
        end_time = None
        if config.get("end_time"):
            end_time = datetime.fromisoformat(config["end_time"])

        initial_balance_val = config.get("initial_balance", "10000.0")
        initial_balance = Decimal(str(initial_balance_val))

        ds_data = config.get("data_source") or {}
        source_type_val = ds_data.get("source_type", "csv")
        try:
            source_type = BacktestDataSourceType(source_type_val)
        except ValueError:
            source_type = BacktestDataSourceType.CSV
        data_source = BacktestDataSourceRequest(
            source_type=source_type,
            path=ds_data.get("path"),
            source_id=ds_data.get("source_id"),
        )

        exec_data = config.get("execution") or {}
        execution = ExecutionConfiguration(
            latency_ms=float(exec_data.get("latency_ms", 500.0)),
            slippage_ticks=int(exec_data.get("slippage_ticks", 2)),
            fee_rate=Decimal(str(exec_data.get("fee_rate", "0.001"))),
        )

        request = BacktestRequest(
            ticker_symbol=dao.ticker_symbol,
            start_time=start_time,
            end_time=end_time,
            data_source=data_source,
            initial_balance=initial_balance,
            execution=execution,
        )
        try:
            status = ExecutionStatus(dao.status)
        except ValueError:
            status = ExecutionStatus.COMPLETED

        return BacktestSession(
            id=dao.id,
            ticker_symbol=dao.ticker_symbol,
            request=request,
            status=status,
            created_at=dao.created_at,
            started_at=dao.started_at or start_time,
            completed_at=dao.completed_at or end_time or dao.updated_at,
            worker_id=dao.worker_id,
            heartbeat_at=dao.heartbeat_at,
            lease_expires_at=dao.lease_expires_at,
            error=dao.error_message,
        )

    @staticmethod
    def _normalize_value(v: Any) -> Any:
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, dict):
            return {k: BacktestDBVSEntityMapper._normalize_value(val) for k, val in v.items()}
        if isinstance(v, list):
            return [BacktestDBVSEntityMapper._normalize_value(item) for item in v]
        return v

    @staticmethod
    def _serialize_metrics(metrics: Optional[BacktestMetrics | dict[str, Any]]) -> dict[str, Any]:
        if metrics is None:
            return {}
        if isinstance(metrics, dict):
            raw_metrics = metrics
        elif isinstance(metrics, BacktestMetrics) or (is_dataclass(metrics) and not isinstance(metrics, type)):
            raw_metrics = asdict(metrics)
        else:
            raw_metrics = {}

        metrics_dict: dict[str, Any] = {
            k: BacktestDBVSEntityMapper._normalize_value(v)
            for k, v in raw_metrics.items()
        }

        for alias, source in (
                ("total_pnl", "absolute_pnl"),
                ("total_trades", "round_trips"),
                ("total_orders", "orders_submitted"),
                ("total_fills", "orders_filled"),
        ):
            if alias not in metrics_dict and source in metrics_dict:
                metrics_dict[alias] = metrics_dict[source]

        return metrics_dict

    @staticmethod
    def _serialize_attribution_metric(metric: AttributionMetrics) -> dict[str, Any]:
        return {
            "total_trades": metric.total_trades,
            "winning_trades": metric.winning_trades,
            "losing_trades": metric.losing_trades,
            "win_rate_pct": metric.win_rate_pct,
            "net_pnl": float(metric.net_pnl),
            "profit_factor": metric.profit_factor,
            "avg_return_pct": metric.avg_return_pct,
            "max_win": float(metric.max_win),
            "max_loss": float(metric.max_loss),
        }

    @staticmethod
    def _serialize_strategy_metrics(result: BacktestResult) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if result.strategy_attribution:
            data["strategy_attribution"] = {
                k: BacktestDBVSEntityMapper._serialize_attribution_metric(v)
                for k, v in result.strategy_attribution.items()
            }
        if result.trades:
            co_matrix, co_counts = TradeAttributionService.compute_co_voting_details(result.trades)
            data["co_voting_matrix"] = co_matrix
            data["co_voting_counts"] = co_counts
            data["co_voting_by_regime"] = TradeAttributionService.compute_co_voting_by_regime(result.trades)
            strat_regime = TradeAttributionService.attribute_strategy_by_regime(result.trades)
            data["strategy_regime_matrix"] = {
                s: {
                    r: BacktestDBVSEntityMapper._serialize_attribution_metric(m)
                    for r, m in r_map.items()
                }
                for s, r_map in strat_regime.items()
            }
            regimes = result.regime_attribution or TradeAttributionService.attribute_by_regime(result.trades)
            data["regime_attribution"] = {
                r: BacktestDBVSEntityMapper._serialize_attribution_metric(m)
                for r, m in regimes.items()
            }
        return data

    @staticmethod
    def result_to_dao(
            result: BacktestResult,
            metrics: Optional[BacktestMetrics | dict[str, Any]] = None,
    ) -> BacktestResultDao:
        metrics_dict = BacktestDBVSEntityMapper._serialize_metrics(metrics)
        metrics_dict.update(BacktestDBVSEntityMapper._serialize_strategy_metrics(result))
        execution_dict = {
            "latency_ms": result.execution.latency_ms,
            "slippage_ticks": result.execution.slippage_ticks,
            "fee_rate": str(result.execution.fee_rate),
        }

        data_dict = {
            "initial_balance": str(result.initial_balance),
            "final_balance": str(result.final_balance),
            "final_equity": str(result.final_equity),
            "total_orders": len(result.orders),
            "total_fills": len(result.fills),
            "execution": execution_dict,
            "metrics": metrics_dict,
        }

        return BacktestResultDao(
            session_id=result.session_id,
            ticker_symbol=result.ticker_symbol,
            data=data_dict,
        )

    @staticmethod
    def dao_to_result(dao: BacktestResultDao) -> BacktestResult:
        data = dao.data or {}
        exec_data = data.get("execution") or {}
        exec_cfg = ExecutionConfiguration(
            latency_ms=float(exec_data.get("latency_ms", 500.0)),
            slippage_ticks=int(exec_data.get("slippage_ticks", 2)),
            fee_rate=Decimal(str(exec_data.get("fee_rate", "0.001"))),
        )

        initial_balance = Decimal(str(data.get("initial_balance", "10000.0")))
        final_balance = Decimal(str(data.get("final_balance", "10000.0")))
        final_equity = Decimal(str(data.get("final_equity", "10000.0")))

        return BacktestResult(
            session_id=dao.session_id,
            ticker_symbol=dao.ticker_symbol,
            initial_balance=initial_balance,
            final_balance=final_balance,
            final_equity=final_equity,
            execution=exec_cfg,
        )
