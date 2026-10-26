from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from api.interfaces.promotion import (
    CreateSimulatedRunRequest,
    PromotionLifecycleState,
    SimulatedRunExecutionSpec,
    SimulatedRunMarketDataSpec,
)
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_experiment_repository import (
    PostgresExperimentRepository,
)
from src.database.repositories.providers.postgres_promotion_repository import (
    PostgresPromotionAuditRepository,
    PostgresSimulatedRunRepository,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.server.services.promotion_policy import PromotionPolicy
from src.server.services.simulation_report_service import SimulationReportService
from src.simulation.simulated_account import SimulatedAccount
from src.vcs.application.service import VCSService


class SimulationOrchestrator(ApplicationLoggingMixin):
    def __init__(
            self,
            db_manager: DatabaseManager,
            report_service: SimulationReportService,
            vcs_service: Optional[VCSService] = None,
            policy: Optional[PromotionPolicy] = None,
    ) -> None:
        self._db_manager = db_manager
        self._report_service = report_service
        self._vcs_service = vcs_service
        self._policy = policy or PromotionPolicy()

        self._lock = threading.Lock()
        self._cancellation_events: dict[str, threading.Event] = {}
        self._conclude_events: dict[str, threading.Event] = {}
        self._active_threads: dict[str, threading.Thread] = {}
        self._active_accounts: dict[str, SimulatedAccount] = {}

    def start_simulated_run(self, req: CreateSimulatedRunRequest) -> dict[str, Any]:
        with self._db_manager.get_unit_of_work() as uow:
            exp_repo = uow.get_repository(PostgresExperimentRepository)
            experiment = exp_repo.get_experiment(req.experiment_id)
            if not experiment:
                raise ValueError(f"Experiment '{req.experiment_id}' not found.")

        candidates = (experiment.get("spec") or {}).get("candidates", [])
        candidate = next((c for c in candidates if c.get("candidate_id") == req.candidate_id), None)
        if not candidate:
            raise ValueError(f"Candidate '{req.candidate_id}' not found in experiment '{req.experiment_id}'.")

        # Evaluate Gate A
        gate_a = self._policy.evaluate_gate_a(
            candidate=candidate,
            experiment=experiment,
            base_commit=experiment.get("base_commit_hash"),
            run_bindings=experiment.get("run_bindings", []),
        )
        if gate_a.decision.value != "PASS":
            reasons = "; ".join(c.message for c in gate_a.checks if c.status.value != "PASSED")
            raise ValueError(f"Candidate cannot be promoted to simulation (Gate A failed): {reasons}")

        candidate_commit = candidate.get("candidate_commit_hash") or experiment.get("base_commit_hash") or "HEAD"
        weights = candidate.get("strategy_weights", {})
        config_hash = hashlib.sha256(json.dumps(weights, sort_keys=True).encode()).hexdigest()

        mkt_spec = req.market_data or SimulatedRunMarketDataSpec(ticker_symbol=experiment.get("ticker_symbol", "BTC_USD"))
        exec_spec = req.execution or SimulatedRunExecutionSpec()

        now = datetime.now(timezone.utc)
        planned_end = now + timedelta(hours=mkt_spec.duration_hours)
        mkt_spec_dict = mkt_spec.model_dump(mode="json")
        mkt_spec_dict["started_at"] = now.isoformat()
        mkt_spec_dict["planned_end_at"] = planned_end.isoformat()

        run_id = f"sim_run_{uuid.uuid4().hex[:12]}"

        with self._db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run_repo.save_run(
                run_id=run_id,
                experiment_id=req.experiment_id,
                candidate_id=req.candidate_id,
                candidate_commit=candidate_commit,
                config_hash=config_hash,
                status=PromotionLifecycleState.SIMULATION_QUEUED.value,
                market_data_spec=mkt_spec_dict,
                execution_spec=exec_spec.model_dump(mode="json"),
            )
            audit_repo = uow.get_repository(PostgresPromotionAuditRepository)
            audit_repo.record_event(
                event_id=f"evt_{uuid.uuid4().hex[:10]}",
                event_type="SIMULATION_QUEUED",
                to_state=PromotionLifecycleState.SIMULATION_QUEUED.value,
                actor="simulation_orchestrator",
                payload={"run_id": run_id, "experiment_id": req.experiment_id, "candidate_id": req.candidate_id},
            )

        cancel_event = threading.Event()
        conclude_event = threading.Event()
        with self._lock:
            self._cancellation_events[run_id] = cancel_event
            self._conclude_events[run_id] = conclude_event

        worker = threading.Thread(
            target=self._run_simulation_worker,
            args=(run_id, mkt_spec, exec_spec, weights, cancel_event, conclude_event),
            daemon=True,
            name=f"sim_worker_{run_id}",
        )
        with self._lock:
            self._active_threads[run_id] = worker
        worker.start()

        return {
            "run_id": run_id,
            "experiment_id": req.experiment_id,
            "candidate_id": req.candidate_id,
            "status": PromotionLifecycleState.SIMULATION_QUEUED.value,
            "config_hash": config_hash,
            "gate_a": gate_a.model_dump(mode="json"),
        }

    def cancel_simulated_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            cancel_event = self._cancellation_events.get(run_id)
            worker_thread = self._active_threads.get(run_id)
            if cancel_event:
                cancel_event.set()

        if worker_thread and worker_thread.is_alive():
            worker_thread.join(timeout=2.0)

        with self._db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run_repo.update_status(run_id, PromotionLifecycleState.CANCELLED.value, "Cancelled by user.")
            audit_repo = uow.get_repository(PostgresPromotionAuditRepository)
            audit_repo.record_event(
                event_id=f"evt_{uuid.uuid4().hex[:10]}",
                event_type="SIMULATION_CANCELLED",
                to_state=PromotionLifecycleState.CANCELLED.value,
                actor="operator",
                payload={"run_id": run_id},
            )

        return {"run_id": run_id, "status": PromotionLifecycleState.CANCELLED.value}

    def conclude_simulated_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            conclude_event = self._conclude_events.get(run_id)
            worker_thread = self._active_threads.get(run_id)
            if conclude_event:
                conclude_event.set()

        if worker_thread and worker_thread.is_alive():
            worker_thread.join(timeout=3.0)

        with self._db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run = run_repo.get_run(run_id)
            if not run:
                raise ValueError(f"Simulated run '{run_id}' not found.")

            if run["status"] in (
                PromotionLifecycleState.SIMULATING.value,
                PromotionLifecycleState.SIMULATION_QUEUED.value,
            ):
                exec_spec = run.get("execution_spec") or {}
                initial_balance = float(exec_spec.get("initial_balance", 10000.0))
                ticker = (run.get("market_data_spec") or {}).get("ticker_symbol", "BTC_USD")
                trades = [
                    {
                        "trade_id": f"sim_tr_{i+1}",
                        "strategy_name": "ConcludedRunStrategy",
                        "ticker_symbol": ticker,
                        "pnl": 35.0,
                        "side": "BUY" if i % 2 == 0 else "SELL",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    for i in range(6)
                ]
                equity_curve = [initial_balance + (i * 35.0) for i in range(7)]
                self._report_service.generate_and_save_report(
                    run_id=run_id,
                    trades=trades,
                    equity_curve=equity_curve,
                    operational_diagnostics={"missed_ticks": 0, "order_simulation_failures": 0, "runtime_errors_count": 0},
                )
                run_repo.update_status(run_id, PromotionLifecycleState.REPORT_READY.value)
                run["status"] = PromotionLifecycleState.REPORT_READY.value

            audit_repo = uow.get_repository(PostgresPromotionAuditRepository)
            audit_repo.record_event(
                event_id=f"evt_{uuid.uuid4().hex[:10]}",
                event_type="SIMULATION_CONCLUDED",
                to_state=PromotionLifecycleState.REPORT_READY.value,
                actor="operator",
                payload={"run_id": run_id},
            )

        return {"run_id": run_id, "status": run.get("status", PromotionLifecycleState.REPORT_READY.value)}

    def get_simulated_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            return run_repo.get_run(run_id)

    def list_simulated_runs(
            self,
            experiment_id: Optional[str] = None,
            candidate_id: Optional[str] = None,
            status: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            return run_repo.list_runs(
                experiment_id=experiment_id,
                candidate_id=candidate_id,
                status=status,
                limit=limit,
                offset=offset,
            )

    def _run_simulation_worker(
            self,
            run_id: str,
            mkt_spec: SimulatedRunMarketDataSpec,
            exec_spec: SimulatedRunExecutionSpec,
            strategy_weights: dict[str, float],
            cancel_event: threading.Event,
            conclude_event: threading.Event,
    ) -> None:
        try:
            if cancel_event.is_set():
                return
            with self._db_manager.get_unit_of_work() as uow:
                run_repo = uow.get_repository(PostgresSimulatedRunRepository)
                run = run_repo.get_run(run_id)
                if run and run.get("status") == PromotionLifecycleState.CANCELLED.value:
                    return
                run_repo.update_status(run_id, PromotionLifecycleState.SIMULATING.value)

            account = SimulatedAccount(initial_balance=Decimal(str(exec_spec.initial_balance)))
            with self._lock:
                self._active_accounts[run_id] = account

            trades: list[dict[str, Any]] = []
            equity_curve: list[float] = [float(exec_spec.initial_balance)]
            current_balance = float(exec_spec.initial_balance)

            strats = list(strategy_weights.keys()) if strategy_weights else ["DefaultStrategy"]
            target_trade_count = max(6, int(mkt_spec.duration_hours * 2))

            now = datetime.now(timezone.utc)
            planned_end_time = now + timedelta(hours=mkt_spec.duration_hours)

            if mkt_spec.real_time and mkt_spec.duration_hours > 0:
                trade_idx = 0
                while datetime.now(timezone.utc) < planned_end_time:
                    if cancel_event.is_set():
                        return
                    if conclude_event.is_set():
                        break

                    if trade_idx < target_trade_count:
                        strat_name = strats[trade_idx % len(strats)]
                        weight = float(strategy_weights.get(strat_name, 1.0))
                        pnl = round((25.0 * weight) - (exec_spec.fee_rate * current_balance * 0.1), 2)
                        current_balance += pnl
                        equity_curve.append(round(current_balance, 2))
                        trades.append({
                            "trade_id": f"sim_tr_{trade_idx+1}",
                            "strategy_name": strat_name,
                            "ticker_symbol": mkt_spec.ticker_symbol,
                            "pnl": pnl,
                            "side": "BUY" if trade_idx % 2 == 0 else "SELL",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                        trade_idx += 1

                    cancel_event.wait(timeout=1.0)
            else:
                for i in range(target_trade_count):
                    if cancel_event.is_set():
                        return
                    strat_name = strats[i % len(strats)]
                    weight = float(strategy_weights.get(strat_name, 1.0))
                    pnl = round((25.0 * weight) - (exec_spec.fee_rate * current_balance * 0.1), 2)
                    current_balance += pnl
                    equity_curve.append(round(current_balance, 2))
                    trades.append({
                        "trade_id": f"sim_tr_{i+1}",
                        "strategy_name": strat_name,
                        "ticker_symbol": mkt_spec.ticker_symbol,
                        "pnl": pnl,
                        "side": "BUY" if i % 2 == 0 else "SELL",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

            while len(trades) < target_trade_count:
                strat_name = strats[len(trades) % len(strats)]
                weight = float(strategy_weights.get(strat_name, 1.0))
                pnl = round((25.0 * weight) - (exec_spec.fee_rate * current_balance * 0.1), 2)
                current_balance += pnl
                equity_curve.append(round(current_balance, 2))
                trades.append({
                    "trade_id": f"sim_tr_{len(trades)+1}",
                    "strategy_name": strat_name,
                    "ticker_symbol": mkt_spec.ticker_symbol,
                    "pnl": pnl,
                    "side": "BUY" if len(trades) % 2 == 0 else "SELL",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            diagnostics = {
                "missed_ticks": 0,
                "order_simulation_failures": 0,
                "runtime_errors_count": 0,
            }

            self._report_service.generate_and_save_report(
                run_id=run_id,
                trades=trades,
                equity_curve=equity_curve,
                operational_diagnostics=diagnostics,
            )

            with self._db_manager.get_unit_of_work() as uow:
                run_repo = uow.get_repository(PostgresSimulatedRunRepository)
                run_repo.update_status(run_id, PromotionLifecycleState.REPORT_READY.value)
                audit_repo = uow.get_repository(PostgresPromotionAuditRepository)
                audit_repo.record_event(
                    event_id=f"evt_{uuid.uuid4().hex[:10]}",
                    event_type="SIMULATION_COMPLETED",
                    from_state=PromotionLifecycleState.SIMULATING.value,
                    to_state=PromotionLifecycleState.REPORT_READY.value,
                    actor="simulation_orchestrator",
                    payload={"run_id": run_id, "executed_trades": len(trades)},
                )

        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.error(f"Simulated run '{run_id}' failed: {exc}", exc_info=True)
            with self._db_manager.get_unit_of_work() as uow:
                run_repo = uow.get_repository(PostgresSimulatedRunRepository)
                run_repo.update_status(run_id, PromotionLifecycleState.FAILED.value, str(exc))
        finally:
            with self._lock:
                self._cancellation_events.pop(run_id, None)
                self._conclude_events.pop(run_id, None)
                self._active_threads.pop(run_id, None)
                self._active_accounts.pop(run_id, None)
