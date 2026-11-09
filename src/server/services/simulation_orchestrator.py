from __future__ import annotations

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
from api.interfaces.trade_action import TradeAction
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_experiment_repository import (
    PostgresExperimentRepository,
)
from src.database.repositories.providers.postgres_promotion_repository import (
    PostgresPromotionAuditRepository,
    PostgresSimulatedRunRepository,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.server.services.canonical_config import CanonicalConfigService
from src.server.services.promotion_policy import PromotionPolicy
from src.server.services.simulation_report_service import SimulationReportService
from src.simulation.simulated_account import SimulatedAccount
from src.simulation.simulated_rest_manager import SimulatedRestManager
from src.vcs.application.service import VCSService


class SimulationOrchestrator(ApplicationLoggingMixin):
    def __init__(
            self,
            db_manager: DatabaseManager,
            report_service: SimulationReportService,
            vcs_service: Optional[VCSService] = None,
            policy: Optional[PromotionPolicy] = None,
            market_data_provider: Optional[Any] = None,
    ) -> None:
        self._db_manager = db_manager
        self._report_service = report_service
        self._vcs_service = vcs_service
        self._policy = policy or PromotionPolicy()
        self._market_data_provider = market_data_provider

        self._lock = threading.Lock()
        self._cancellation_events: dict[str, threading.Event] = {}
        self._conclude_events: dict[str, threading.Event] = {}
        self._active_threads: dict[str, threading.Thread] = {}
        self._active_accounts: dict[str, SimulatedAccount] = {}

    def start_simulated_run(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
            self,
            req: CreateSimulatedRunRequest,
    ) -> dict[str, Any]:
        with self._db_manager.get_unit_of_work() as uow:
            exp_repo = uow.get_repository(PostgresExperimentRepository)
            experiment = exp_repo.get_experiment(req.experiment_id)
            if not experiment:
                raise ValueError(f"Experiment '{req.experiment_id}' not found.")

        candidates = (experiment.get("spec") or {}).get("candidates", [])
        candidate = next((c for c in candidates if c.get("candidate_id") == req.candidate_id), None)
        if not candidate:
            raise ValueError(f"Candidate '{req.candidate_id}' not found in experiment '{req.experiment_id}'.")

        base_commit = experiment.get("base_commit_hash")
        if not base_commit and self._vcs_service:
            try:
                base_commit = self._vcs_service.resolve_commit_hash("refs/heads/main")
            except Exception:
                base_commit = None

        candidate_commit = candidate.get("candidate_commit_hash") or base_commit
        CanonicalConfigService.validate_commit_hash(candidate_commit)

        gate_a = self._policy.evaluate_gate_a(
            candidate=candidate,
            experiment=experiment,
            base_commit=candidate_commit,
            run_bindings=experiment.get("run_bindings", []),
        )
        if gate_a.decision.value != "PASS":
            reasons = "; ".join(c.message for c in gate_a.checks if c.status.value != "PASSED")
            raise ValueError(f"Candidate cannot be promoted to simulation (Gate A failed): {reasons}")

        base_config: dict[str, Any] = {}
        if self._vcs_service and base_commit:
            try:
                base_config = self._vcs_service.checkout(base_commit)
            except Exception:
                base_config = {}

        default_ticker = experiment.get("ticker_symbol", "BTC_USD")
        mkt_spec = req.market_data or SimulatedRunMarketDataSpec(ticker_symbol=default_ticker)
        exec_spec = req.execution or SimulatedRunExecutionSpec()

        if mkt_spec.duration_hours <= 0:
            raise ValueError("Simulation duration_hours must be positive.")

        now = datetime.now(timezone.utc)
        planned_end = now + timedelta(hours=mkt_spec.duration_hours)
        mkt_spec_dict = mkt_spec.model_dump(mode="json")
        mkt_spec_dict["started_at"] = now.isoformat()
        mkt_spec_dict["planned_end_at"] = planned_end.isoformat()

        candidate_source = candidate
        if self._vcs_service and candidate_commit:
            try:
                candidate_checkout = self._vcs_service.checkout(candidate_commit)
                if candidate_checkout and isinstance(candidate_checkout.get("assets"), list):
                    candidate_source = candidate_checkout
            except Exception:
                candidate_source = candidate

        candidate_effective_config = CanonicalConfigService.build_effective_config(
            candidate_source,
            experiment,
            execution_spec=exec_spec.model_dump(mode="json"),
            market_data_spec=mkt_spec_dict,
        )
        candidate_config_hash = CanonicalConfigService.compute_hash(candidate_effective_config)

        target_ticker = (
            candidate.get("ticker_symbol")
            or experiment.get("ticker_symbol")
            or mkt_spec.ticker_symbol
            or default_ticker
        )
        baseline_candidate = {}
        if base_config and isinstance(base_config.get("assets"), list):
            matching_asset = next(
                (
                    a for a in base_config["assets"]
                    if isinstance(a, dict) and a.get("ticker_symbol") == target_ticker
                ),
                {},
            )
            if matching_asset:
                baseline_candidate = matching_asset

        baseline_effective_config = CanonicalConfigService.build_effective_config(
            baseline_candidate,
            base_config or experiment,
            execution_spec=exec_spec.model_dump(mode="json"),
            market_data_spec=mkt_spec_dict,
        )
        baseline_config_hash = CanonicalConfigService.compute_hash(baseline_effective_config)

        run_id = f"sim_run_{uuid.uuid4().hex[:12]}"
        baseline_run_id = f"sim_base_{uuid.uuid4().hex[:12]}"

        with self._db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run_repo.save_run(
                run_id=baseline_run_id,
                experiment_id=req.experiment_id,
                candidate_id="__baseline_main__",
                candidate_commit=base_commit or candidate_commit,
                config_hash=baseline_config_hash,
                status=PromotionLifecycleState.SIMULATION_QUEUED.value,
                market_data_spec=mkt_spec_dict,
                execution_spec=exec_spec.model_dump(mode="json"),
                effective_config=baseline_effective_config,
                baseline_run_id=None,
            )
            run_repo.save_run(
                run_id=run_id,
                experiment_id=req.experiment_id,
                candidate_id=req.candidate_id,
                candidate_commit=candidate_commit,
                config_hash=candidate_config_hash,
                status=PromotionLifecycleState.SIMULATION_QUEUED.value,
                market_data_spec=mkt_spec_dict,
                execution_spec=exec_spec.model_dump(mode="json"),
                effective_config=candidate_effective_config,
                baseline_run_id=baseline_run_id,
            )
            audit_repo = uow.get_repository(PostgresPromotionAuditRepository)
            audit_repo.record_event(
                event_id=f"evt_{uuid.uuid4().hex[:10]}",
                event_type="SIMULATION_QUEUED",
                to_state=PromotionLifecycleState.SIMULATION_QUEUED.value,
                actor="simulation_orchestrator",
                payload={
                    "run_id": run_id,
                    "experiment_id": req.experiment_id,
                    "candidate_id": req.candidate_id,
                    "baseline_run_id": baseline_run_id,
                },
            )

        cancel_event = threading.Event()
        conclude_event = threading.Event()
        with self._lock:
            self._cancellation_events[run_id] = cancel_event
            self._conclude_events[run_id] = conclude_event

        worker = threading.Thread(
            target=self._run_simulation_worker,
            args=(
                run_id,
                baseline_run_id,
                mkt_spec,
                exec_spec,
                candidate_effective_config,
                baseline_effective_config,
                cancel_event,
                conclude_event,
            ),
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
            "config_hash": candidate_config_hash,
            "baseline_run_id": baseline_run_id,
            "gate_a": gate_a.model_dump(mode="json"),
        }

    def cancel_simulated_run(self, run_id: str) -> dict[str, Any]:
        with self._db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run = run_repo.get_run(run_id)
            if not run:
                raise ValueError(f"Simulated run '{run_id}' not found.")
            if run.get("candidate_id") == "__baseline_main__":
                raise ValueError(
                    f"Direct cancellation of baseline run '{run_id}' is not permitted. "
                    "Cancel the parent simulation run instead."
                )

        with self._lock:
            cancel_event = self._cancellation_events.get(run_id)
            worker_thread = self._active_threads.get(run_id)
            if cancel_event:
                cancel_event.set()

        if worker_thread and worker_thread.is_alive():
            worker_thread.join(timeout=3.0)

        with self._db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run = run_repo.get_run(run_id)
            if run and run.get("status") not in (
                PromotionLifecycleState.CANCELLED.value,
                PromotionLifecycleState.FAILED.value,
            ):
                run_repo.update_status(run_id, PromotionLifecycleState.CANCELLED.value, "Cancelled by user.")
                if run.get("baseline_run_id"):
                    run_repo.update_status(
                        run["baseline_run_id"],
                        PromotionLifecycleState.CANCELLED.value,
                        "Cancelled by user.",
                    )
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
            worker_thread.join(timeout=5.0)

        with self._db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run = run_repo.get_run(run_id)
            if not run:
                raise ValueError(f"Simulated run '{run_id}' not found.")

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

    def recover_interrupted_runs(self) -> int:
        with self._db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            audit_repo = uow.get_repository(PostgresPromotionAuditRepository)
            recovered_count = 0
            page_size = 200
            offset = 0
            while True:
                active_runs = run_repo.list_runs(limit=page_size, offset=offset)
                if not active_runs:
                    break
                for run in active_runs:
                    if run.get("status") in (
                        PromotionLifecycleState.SIMULATING.value,
                        PromotionLifecycleState.SIMULATION_QUEUED.value,
                    ):
                        run_id = run["run_id"]
                        run_repo.update_status(
                            run_id,
                            PromotionLifecycleState.FAILED.value,
                            "Run was interrupted by server shutdown/restart.",
                        )
                        audit_repo.record_event(
                            event_id=f"evt_{uuid.uuid4().hex[:10]}",
                            event_type="SIMULATION_FAILED",
                            from_state=run["status"],
                            to_state=PromotionLifecycleState.FAILED.value,
                            actor="system_startup_recovery",
                            payload={"run_id": run_id, "reason": "server_restart"},
                        )
                        recovered_count += 1
                if len(active_runs) < page_size:
                    break
                offset += page_size
            return recovered_count

    def _run_simulation_worker(  # pylint: disable=too-many-locals,too-many-statements,too-many-branches
            self,
            run_id: str,
            baseline_run_id: str,
            mkt_spec: SimulatedRunMarketDataSpec,
            exec_spec: SimulatedRunExecutionSpec,
            candidate_effective_config: dict[str, Any],
            baseline_effective_config: dict[str, Any],
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
                if baseline_run_id:
                    run_repo.update_status(baseline_run_id, PromotionLifecycleState.SIMULATING.value)

            initial_balance = Decimal(str(exec_spec.initial_balance))
            cand_account = SimulatedAccount(initial_balance=initial_balance)
            cand_rest = SimulatedRestManager(cand_account, market_data_provider=self._market_data_provider)

            base_account = SimulatedAccount(initial_balance=initial_balance)
            base_rest = SimulatedRestManager(base_account, market_data_provider=self._market_data_provider)

            with self._lock:
                self._active_accounts[run_id] = cand_account
                if baseline_run_id:
                    self._active_accounts[baseline_run_id] = base_account

            ticker = mkt_spec.ticker_symbol or "BTC_USD"
            parts = ticker.split("_") if "_" in ticker else (ticker.split("-") if "-" in ticker else ticker.split("/"))
            base_curr = parts[0] if len(parts) == 2 else "BTC"
            quote_curr = parts[1] if len(parts) == 2 else "USD"

            slippage_ticks = 1 if exec_spec.slippage_ticks is None else exec_spec.slippage_ticks
            slippage = float(slippage_ticks) * 0.0001

            fee_rate = 0.001 if exec_spec.fee_rate is None else float(exec_spec.fee_rate)

            effective_duration = max(0.1, float(mkt_spec.duration_hours))
            target_trades = max(6, int(effective_duration * 2))

            cand_equity_curve: list[float] = [float(exec_spec.initial_balance)]
            base_equity_curve: list[float] = [float(exec_spec.initial_balance)]
            cand_trades: list[dict[str, Any]] = []
            base_trades: list[dict[str, Any]] = []
            cand_lots: list[tuple[float, float]] = []
            base_lots: list[tuple[float, float]] = []

            base_mkt_price = 50000.0
            step_idx = 0
            planned_end = datetime.now(timezone.utc) + timedelta(hours=effective_duration)

            diagnostics = {
                "missed_ticks": 0,
                "order_simulation_failures": 0,
                "runtime_errors_count": 0,
                "telemetry_available": True,
            }

            while True:
                if cancel_event.is_set():
                    self._mark_cancelled(run_id, baseline_run_id)
                    return
                if conclude_event.is_set():
                    break
                if mkt_spec.real_time and datetime.now(timezone.utc) >= planned_end:
                    break
                if not mkt_spec.real_time and step_idx >= target_trades:
                    break

                tick_price = self._fetch_tick_price(
                    cand_rest,
                    ticker,
                    base_mkt_price,
                    step_idx,
                    diagnostics,
                )

                self._execute_simulated_step(
                    step_idx=step_idx,
                    ticker=ticker,
                    base_curr=base_curr,
                    quote_curr=quote_curr,
                    tick_price=tick_price,
                    slippage=slippage,
                    fee_rate=fee_rate,
                    effective_config=candidate_effective_config,
                    rest_manager=cand_rest,
                    account=cand_account,
                    inventory_lots=cand_lots,
                    trades_out=cand_trades,
                    equity_out=cand_equity_curve,
                    prefix="cand",
                    diagnostics=diagnostics,
                )

                self._execute_simulated_step(
                    step_idx=step_idx,
                    ticker=ticker,
                    base_curr=base_curr,
                    quote_curr=quote_curr,
                    tick_price=tick_price,
                    slippage=slippage,
                    fee_rate=fee_rate,
                    effective_config=baseline_effective_config,
                    rest_manager=base_rest,
                    account=base_account,
                    inventory_lots=base_lots,
                    trades_out=base_trades,
                    equity_out=base_equity_curve,
                    prefix="base",
                    diagnostics=diagnostics,
                )

                step_idx += 1
                if mkt_spec.real_time:
                    cancel_event.wait(timeout=1.0)

            self._report_service.generate_and_save_report(
                run_id=run_id,
                trades=cand_trades,
                equity_curve=cand_equity_curve,
                operational_diagnostics=diagnostics,
                baseline_trades=base_trades,
                baseline_equity_curve=base_equity_curve,
            )

            if baseline_run_id:
                self._report_service.generate_and_save_report(
                    run_id=baseline_run_id,
                    trades=base_trades,
                    equity_curve=base_equity_curve,
                    operational_diagnostics=diagnostics,
                )

            with self._db_manager.get_unit_of_work() as uow:
                run_repo = uow.get_repository(PostgresSimulatedRunRepository)
                run_repo.update_status(run_id, PromotionLifecycleState.REPORT_READY.value)
                if baseline_run_id:
                    run_repo.update_status(baseline_run_id, PromotionLifecycleState.REPORT_READY.value)
                audit_repo = uow.get_repository(PostgresPromotionAuditRepository)
                audit_repo.record_event(
                    event_id=f"evt_{uuid.uuid4().hex[:10]}",
                    event_type="SIMULATION_COMPLETED",
                    from_state=PromotionLifecycleState.SIMULATING.value,
                    to_state=PromotionLifecycleState.REPORT_READY.value,
                    actor="simulation_orchestrator",
                    payload={"run_id": run_id, "executed_trades": len(cand_trades)},
                )

        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.error(f"Simulated run '{run_id}' failed: {exc}", exc_info=True)
            with self._db_manager.get_unit_of_work() as uow:
                run_repo = uow.get_repository(PostgresSimulatedRunRepository)
                run_repo.update_status(run_id, PromotionLifecycleState.FAILED.value, str(exc))
                if baseline_run_id:
                    run_repo.update_status(baseline_run_id, PromotionLifecycleState.FAILED.value, str(exc))
        finally:
            with self._lock:
                self._cancellation_events.pop(run_id, None)
                self._conclude_events.pop(run_id, None)
                self._active_threads.pop(run_id, None)
                self._active_accounts.pop(run_id, None)
                if baseline_run_id:
                    self._active_accounts.pop(baseline_run_id, None)

    @staticmethod
    def _extract_strategy_weights(config: dict[str, Any], default_name: str) -> dict[str, float]:
        strategies = config.get("strategies") or []
        weights: dict[str, float] = {}
        if isinstance(strategies, list):
            for s in strategies:
                if isinstance(s, dict) and s.get("name"):
                    weights[s["name"]] = float(s.get("weight", 1.0))
        if not weights and config.get("strategy_weights"):
            weights = {str(k): float(v) for k, v in config["strategy_weights"].items()}
        return weights or {default_name: 1.0}

    def _mark_cancelled(self, run_id: str, baseline_run_id: Optional[str]) -> None:
        with self._db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run_repo.update_status(run_id, PromotionLifecycleState.CANCELLED.value, "Cancelled by user.")
            if baseline_run_id:
                run_repo.update_status(baseline_run_id, PromotionLifecycleState.CANCELLED.value, "Cancelled by user.")
            audit_repo = uow.get_repository(PostgresPromotionAuditRepository)
            audit_repo.record_event(
                event_id=f"evt_{uuid.uuid4().hex[:10]}",
                event_type="SIMULATION_CANCELLED",
                to_state=PromotionLifecycleState.CANCELLED.value,
                actor="operator",
                payload={"run_id": run_id},
            )

    @staticmethod
    def _fetch_tick_price(
            rest_manager: SimulatedRestManager,
            ticker: str,
            base_mkt_price: float,
            step_idx: int,
            diagnostics: dict[str, Any],
    ) -> float:
        try:
            mkt = rest_manager.get_market_data("BINANCE", ticker)
            if mkt and mkt.close_price and float(mkt.close_price) > 0:
                return float(mkt.close_price)
        except Exception:
            pass
        diagnostics["missed_ticks"] = int(diagnostics.get("missed_ticks", 0)) + 1
        diagnostics["telemetry_available"] = False
        return round(base_mkt_price * (1.0 + 0.002 * ((step_idx % 7) - 3)), 2)

    @staticmethod
    def _execute_simulated_step(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches,too-many-statements
            step_idx: int,
            ticker: str,
            base_curr: str,
            quote_curr: str,
            tick_price: float,
            slippage: float,
            fee_rate: float,
            effective_config: dict[str, Any],
            rest_manager: SimulatedRestManager,
            account: SimulatedAccount,
            inventory_lots: list[tuple[float, float]],
            trades_out: list[dict[str, Any]],
            equity_out: list[float],
            prefix: str,
            diagnostics: dict[str, Any],
    ) -> None:
        cash = float(account.get_balance(quote_curr))
        crypto = float(account.get_balance(base_curr))
        current_equity = round(cash + (crypto * tick_price), 2)

        protection = effective_config.get("protection") or {}
        circuit_breaker = bool(protection.get("circuit_breaker", True))
        max_dd_limit = float(protection.get("max_drawdown_limit_pct", 15.0))
        peak_equity = max(equity_out) if equity_out else current_equity
        dd_pct = ((peak_equity - current_equity) / peak_equity) * 100.0 if peak_equity > 0 else 0.0
        if circuit_breaker and dd_pct >= max_dd_limit:
            equity_out.append(current_equity)
            return

        strategies = effective_config.get("strategies") or []
        if not strategies:
            equity_out.append(current_equity)
            return

        is_buy = step_idx % 2 == 0
        action = TradeAction.BUY if is_buy else TradeAction.SELL
        action_key = "buy" if is_buy else "sell"

        accumulated_weight = 0.0
        winning_strat = None
        for s in strategies:
            if not isinstance(s, dict):
                continue
            if s.get("enabled", True) is False:
                continue
            w = float(s.get("weight", 1.0))
            if w <= 0.0:
                continue
            expr = str(s.get("expression", "")).strip().lower()
            if expr in ("false", "0", "none"):
                continue
            strat_action = str(s.get("action", "")).upper()
            if strat_action and strat_action != action.value:
                continue
            accumulated_weight += w
            if winning_strat is None:
                winning_strat = (str(s.get("name", "Strategy")), w)
            elif w > winning_strat[1]:
                winning_strat = (str(s.get("name", "Strategy")), w)

        consensus = effective_config.get("consensus") or {}
        required_consensus = float(consensus.get(action_key, 1.0))
        if accumulated_weight < required_consensus or winning_strat is None:
            equity_out.append(current_equity)
            return

        strat = winning_strat[0]
        weight = accumulated_weight

        adj_price = tick_price * (1.0 + slippage if is_buy else 1.0 - slippage)
        order_price = Decimal(str(round(adj_price, 2)))
        order_uuid = f"ord_{prefix}_{step_idx+1}_{uuid.uuid4().hex[:6]}"

        if is_buy:
            trade_value = Decimal(str(round(400.0 * weight, 2)))
            available_quote = account.get_balance(quote_curr)
            if available_quote < trade_value:
                trade_value = max(Decimal("10.0"), available_quote * Decimal("0.5"))
            qty = Decimal(str(round(float(trade_value) / float(order_price), 4)))
        else:
            available_base = account.get_balance(base_curr)
            if available_base > Decimal("0.001"):
                qty = Decimal(str(round(float(available_base) * 0.5, 4)))
            else:
                qty = Decimal("0.0")

        if qty > Decimal("0.0"):
            try:
                rest_manager.place_order(
                    exchange="BINANCE",
                    uuid=order_uuid,
                    ticker_symbol=ticker,
                    quantity=str(qty),
                    price=order_price,
                    trade_action=action,
                    metadata={"winning_strategy": strat},
                )
                fee = Decimal(str(round(float(qty) * float(order_price) * fee_rate, 4)))
                account.update_balance(quote_curr, -fee)

                if is_buy:
                    inventory_lots.append((float(qty), float(order_price)))
                    pnl = -round(float(fee), 2)
                else:
                    remaining_to_sell = float(qty)
                    cost_basis = 0.0
                    while remaining_to_sell > 1e-6 and inventory_lots:
                        lot_qty, lot_price = inventory_lots[0]
                        matched_qty = min(remaining_to_sell, lot_qty)
                        cost_basis += matched_qty * lot_price
                        remaining_to_sell -= matched_qty
                        if lot_qty <= matched_qty + 1e-6:
                            inventory_lots.pop(0)
                        else:
                            inventory_lots[0] = (lot_qty - matched_qty, lot_price)
                    gross_proceeds = float(qty) * float(order_price)
                    pnl = round(gross_proceeds - cost_basis - float(fee), 2)

                trades_out.append({
                    "trade_id": order_uuid,
                    "strategy_name": strat,
                    "ticker_symbol": ticker,
                    "pnl": pnl,
                    "side": action.value,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:  # pylint: disable=broad-except
                diagnostics["order_simulation_failures"] = (
                    int(diagnostics.get("order_simulation_failures", 0)) + 1
                )
                diagnostics["runtime_errors_count"] = (
                    int(diagnostics.get("runtime_errors_count", 0)) + 1
                )

        cash = float(account.get_balance(quote_curr))
        crypto = float(account.get_balance(base_curr))
        equity = round(cash + (crypto * tick_price), 2)
        equity_out.append(equity)
