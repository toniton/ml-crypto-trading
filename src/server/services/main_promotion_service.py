from __future__ import annotations

import uuid
from typing import Any, Optional

from api.interfaces.promotion import (
    GateDecision,
    PromoteToMainRequest,
    PromotionLifecycleState,
)
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_experiment_repository import (
    PostgresExperimentRepository,
)
from src.database.repositories.providers.postgres_promotion_repository import (
    PostgresPromotionAuditRepository,
    PostgresPromotionRecordRepository,
    PostgresSimulatedRunRepository,
    PostgresSimulationReportRepository,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.server.services.canonical_config import CanonicalConfigService
from src.server.services.promotion_policy import PromotionPolicy
from src.vcs.application.service import VCSService


class MainPromotionService(ApplicationLoggingMixin):
    def __init__(
            self,
            db_manager: DatabaseManager,
            vcs_service: VCSService,
            policy: Optional[PromotionPolicy] = None,
    ) -> None:
        self._db_manager = db_manager
        self._vcs_service = vcs_service
        self._policy = policy or PromotionPolicy()

    def preview_promotion(self, req: PromoteToMainRequest) -> dict[str, Any]:
        exp = self._get_experiment(req.experiment_id)
        candidate, source_commit = self._get_candidate_and_commit(exp, req.candidate_id)
        report = self._get_and_validate_report(
            experiment=exp,
            candidate=candidate,
            source_commit=source_commit,
            report_id=req.report_id,
            run_id=req.run_id,
        )

        merge_preview = self._vcs_service.preview_merge(
            source_ref_or_commit=source_commit,
            target_ref=req.target_ref,
        )

        if isinstance(merge_preview, dict):
            can_ff = bool(merge_preview.get("can_fast_forward", False))
            raw_conflicts = merge_preview.get("conflicts", [])
            base_hash = merge_preview.get("merge_base_hash")
        else:
            can_ff = bool(merge_preview.can_fast_forward)
            raw_conflicts = merge_preview.conflicts or []
            base_hash = merge_preview.merge_base_hash

        conflicts = [
            c if isinstance(c, dict) else vars(c)
            for c in raw_conflicts
        ]
        preview_dict = {
            "can_fast_forward": can_ff,
            "conflicts": conflicts,
            "merge_base_hash": base_hash,
        }

        gate_c = self._policy.evaluate_gate_c(
            approver=req.approver,
            merge_preview=preview_dict,
            config_hash_match=True,
        )

        return {
            "eligible": gate_c.decision == GateDecision.PASS,
            "gate_c": gate_c.model_dump(mode="json"),
            "merge_preview": preview_dict,
            "source_commit": source_commit,
            "target_ref": req.target_ref,
            "config_hash": report.get("config_hash"),
        }

    def promote_to_main(
            self,
            req: PromoteToMainRequest,
            resolved_config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        # Enforce idempotency: return existing successful promotion if already processed
        with self._db_manager.get_unit_of_work() as uow:
            promo_repo = uow.get_repository(PostgresPromotionRecordRepository)
            existing = promo_repo.get_by_idempotency_key(req.idempotency_key)
            if existing and existing.get("status") == PromotionLifecycleState.PROMOTED.value:
                self.app_logger.info(
                    "Promotion with idempotency key '%s' already executed (promo_id %s). Returning existing record.",
                    req.idempotency_key,
                    existing["promotion_id"],
                )
                return existing

        exp = self._get_experiment(req.experiment_id)
        candidate, source_commit = self._get_candidate_and_commit(exp, req.candidate_id)
        report = self._get_and_validate_report(
            experiment=exp,
            candidate=candidate,
            source_commit=source_commit,
            report_id=req.report_id,
            run_id=req.run_id,
        )

        preview_result = self.preview_promotion(req)
        gate_c = preview_result["gate_c"]

        checks_by_name = {c["name"]: c for c in gate_c.get("checks", [])}
        approver_check = checks_by_name.get("authorized_approver")
        hash_check = checks_by_name.get("evidence_hash_match")
        conflict_check = checks_by_name.get("merge_conflict_free")

        if approver_check and approver_check.get("status") != "PASSED":
            raise ValueError(f"Promotion blocked: {approver_check.get('message')}")

        if hash_check and hash_check.get("status") != "PASSED":
            raise ValueError(f"Promotion blocked: {hash_check.get('message')}")

        if conflict_check and conflict_check.get("status") != "PASSED":
            if not resolved_config:
                raise ValueError(f"Promotion blocked: {conflict_check.get('message')}")

        if resolved_config:
            with self._db_manager.get_unit_of_work() as uow:
                run_repo = uow.get_repository(PostgresSimulatedRunRepository)
                run_data = run_repo.get_run(req.run_id)
            resolved_effective = CanonicalConfigService.build_effective_config(
                candidate=resolved_config,
                experiment=exp,
                execution_spec=run_data.get("execution_spec") if run_data else {},
                market_data_spec=run_data.get("market_data_spec") if run_data else {},
            )
            resolved_hash = CanonicalConfigService.compute_hash(resolved_effective)
            if resolved_hash != report.get("config_hash"):
                raise ValueError(
                    f"Resolved configuration hash '{resolved_hash}' does not match "
                    f"simulation report evidence hash '{report.get('config_hash')}'. "
                    "Simulation evidence is required for resolved configuration before promotion."
                )

        merge_message = (
            f"Promote candidate '{candidate.get('name', req.candidate_id)}' "
            f"from experiment '{req.experiment_id}' to {req.target_ref}\n\n"
            f"Approver: {req.approver}\n"
            f"Report: {req.report_id} (run {req.run_id})\n"
            f"Config Hash: {report.get('config_hash')}\n"
            f"Notes: {req.approval_notes or 'None'}"
        )

        merge_result = self._vcs_service.merge(
            source_ref_or_commit=source_commit,
            target_ref=req.target_ref,
            author=req.approver,
            message=merge_message,
            resolved_config=resolved_config,
        )

        if isinstance(merge_result, dict):
            merge_commit = merge_result.get("merge_commit_hash")
        else:
            merge_commit = merge_result.merge_commit_hash
        promotion_id = f"promo_{uuid.uuid4().hex[:12]}"

        with self._db_manager.get_unit_of_work() as uow:
            promo_repo = uow.get_repository(PostgresPromotionRecordRepository)
            promo_repo.save_promotion(
                promotion_id=promotion_id,
                idempotency_key=req.idempotency_key,
                experiment_id=req.experiment_id,
                candidate_id=req.candidate_id,
                source_commit=source_commit,
                target_ref=req.target_ref,
                status=PromotionLifecycleState.PROMOTED.value,
                approver=req.approver,
                approval_notes=req.approval_notes,
                gate_results={"gate_c": gate_c, "merge_commit": merge_commit},
                merge_commit_hash=merge_commit,
                report_id=req.report_id,
                run_id=req.run_id,
                config_hash=report.get("config_hash"),
            )

            audit_repo = uow.get_repository(PostgresPromotionAuditRepository)
            audit_repo.record_event(
                event_id=f"evt_{uuid.uuid4().hex[:10]}",
                promotion_id=promotion_id,
                event_type="PROMOTED_TO_MAIN",
                from_state=PromotionLifecycleState.PROMOTION_ELIGIBLE.value,
                to_state=PromotionLifecycleState.PROMOTED.value,
                actor=req.approver,
                payload={
                    "experiment_id": req.experiment_id,
                    "candidate_id": req.candidate_id,
                    "report_id": req.report_id,
                    "run_id": req.run_id,
                    "config_hash": report.get("config_hash"),
                    "source_commit": source_commit,
                    "merge_commit": merge_commit,
                    "target_ref": req.target_ref,
                },
            )

        self.app_logger.info(
            "Successfully promoted candidate %s (experiment %s) to %s at commit %s. "
            "Live trading safeguards remain active.",
            req.candidate_id,
            req.experiment_id,
            req.target_ref,
            merge_commit,
        )

        return {
            "promotion_id": promotion_id,
            "idempotency_key": req.idempotency_key,
            "experiment_id": req.experiment_id,
            "candidate_id": req.candidate_id,
            "report_id": req.report_id,
            "run_id": req.run_id,
            "config_hash": report.get("config_hash"),
            "status": PromotionLifecycleState.PROMOTED.value,
            "merge_commit_hash": merge_commit,
            "approver": req.approver,
            "live_trading_status": "UNTOUCHED_SAFEGUARDED",
        }

    def list_audit_events(
            self,
            promotion_id: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            audit_repo = uow.get_repository(PostgresPromotionAuditRepository)
            return audit_repo.list_events(promotion_id=promotion_id, limit=limit, offset=offset)

    def _get_experiment(self, experiment_id: str) -> dict[str, Any]:
        with self._db_manager.get_unit_of_work() as uow:
            exp_repo = uow.get_repository(PostgresExperimentRepository)
            exp = exp_repo.get_experiment(experiment_id)
            if not exp:
                raise ValueError(f"Experiment '{experiment_id}' not found.")
            return exp

    def _get_candidate_and_commit(self, exp: dict[str, Any], candidate_id: str) -> tuple[dict[str, Any], str]:
        candidates = (exp.get("spec") or {}).get("candidates", [])
        candidate = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)
        if not candidate:
            raise ValueError(f"Candidate '{candidate_id}' not found in experiment '{exp.get('experiment_id')}'.")

        source_commit = candidate.get("candidate_commit_hash") or exp.get("base_commit_hash")
        if not source_commit:
            raise ValueError(f"Candidate '{candidate_id}' has no committed source hash.")

        return candidate, source_commit

    def _get_and_validate_report(
            self,
            experiment: dict[str, Any],
            candidate: dict[str, Any],
            source_commit: str,
            report_id: str,
            run_id: str,
    ) -> dict[str, Any]:
        with self._db_manager.get_unit_of_work() as uow:
            rep_repo = uow.get_repository(PostgresSimulationReportRepository)
            report = rep_repo.get_report(report_id)
            if not report:
                raise ValueError(f"Simulation report '{report_id}' not found.")

            if report.get("run_id") != run_id:
                raise ValueError(
                    f"Report '{report_id}' is associated with run '{report.get('run_id')}', not '{run_id}'."
                )

            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            run = run_repo.get_run(run_id)
            if not run:
                raise ValueError(f"Simulated run '{run_id}' not found.")

        if report.get("decision") != GateDecision.PASS.value:
            raise ValueError(
                f"Candidate promotion blocked: Simulation report '{report_id}' has decision "
                f"'{report.get('decision')}', must be 'PASS'."
            )

        if run.get("experiment_id") != experiment.get("experiment_id"):
            raise ValueError(
                f"Simulation run belongs to experiment '{run.get('experiment_id')}', "
                f"not '{experiment.get('experiment_id')}'."
            )

        if run.get("candidate_id") != candidate.get("candidate_id"):
            raise ValueError(
                f"Simulation report belongs to candidate '{run.get('candidate_id')}', "
                f"not '{candidate.get('candidate_id')}'."
            )

        if run.get("candidate_commit") != source_commit:
            raise ValueError(
                f"Simulation run commit '{run.get('candidate_commit')}' "
                f"does not match candidate source commit '{source_commit}'."
            )

        current_effective_config = CanonicalConfigService.build_effective_config(
            candidate=candidate,
            experiment=experiment,
            execution_spec=run.get("execution_spec"),
            market_data_spec=run.get("market_data_spec"),
        )
        current_hash = CanonicalConfigService.compute_hash(current_effective_config)
        if report.get("config_hash") != current_hash:
            raise ValueError(
                f"Candidate configuration hash mismatch: report hash '{report.get('config_hash')}' "
                f"!= current configuration hash '{current_hash}'."
            )

        return report
