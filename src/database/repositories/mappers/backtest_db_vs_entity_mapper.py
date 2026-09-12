from __future__ import annotations

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
from src.backtest.domain.session import BacktestSession, BacktestSessionStatus
from src.database.dao.backtest_result_dao import BacktestResultDao
from src.database.dao.backtest_session_dao import BacktestSessionDao


class BacktestDBVSEntityMapper:

    @staticmethod
    def session_to_dao(session: BacktestSession) -> BacktestSessionDao:
        status_str = session.status.value if hasattr(session.status, "value") else str(session.status)
        config_dict: dict[str, Any] = {}
        if session.request:
            config_dict = {
                "start_time": session.request.start_time.isoformat() if session.request.start_time else None,
                "end_time": session.request.end_time.isoformat() if session.request.end_time else None,
                "initial_balance": str(session.request.initial_balance),
                "data_source": {
                    "source_type": session.request.data_source.source_type.value if session.request.data_source else "csv",
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
            status = BacktestSessionStatus(dao.status)
        except ValueError:
            status = BacktestSessionStatus.COMPLETED

        return BacktestSession(
            id=dao.id,
            ticker_symbol=dao.ticker_symbol,
            request=request,
            status=status,
            created_at=dao.created_at,
            started_at=start_time,
            completed_at=end_time or dao.updated_at,
        )

    @staticmethod
    def result_to_dao(
            result: BacktestResult,
            metrics: Optional[BacktestMetrics | dict[str, Any]] = None,
    ) -> BacktestResultDao:
        metrics_dict: dict[str, Any] = {}
        if metrics is not None:
            raw_metrics = (
                metrics if isinstance(metrics, dict)
                else getattr(metrics, "__dict__", {})
            )
            for k, v in raw_metrics.items():
                if isinstance(v, Decimal):
                    metrics_dict[k] = str(v)
                else:
                    metrics_dict[k] = v

            if "total_pnl" not in metrics_dict and "absolute_pnl" in metrics_dict:
                metrics_dict["total_pnl"] = metrics_dict["absolute_pnl"]
            if "total_trades" not in metrics_dict and "round_trips" in metrics_dict:
                metrics_dict["total_trades"] = metrics_dict["round_trips"]
            if "total_orders" not in metrics_dict and "orders_submitted" in metrics_dict:
                metrics_dict["total_orders"] = metrics_dict["orders_submitted"]
            if "total_fills" not in metrics_dict and "orders_filled" in metrics_dict:
                metrics_dict["total_fills"] = metrics_dict["orders_filled"]

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
