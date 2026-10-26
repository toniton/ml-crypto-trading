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
        candidate, source_commit = self._get_candidate_and_commit(req.experiment_id, req.candidate_id)
        report = self._get_latest_passing_report(req.experiment_id, req.candidate_id)
        if not report or report.get("decision") != GateDecision.PASS.value:
            raise ValueError(
                f"Candidate '{req.candidate_id}' cannot be previewed for promotion: "
                "no completed simulated run with passing Gate B evidence was found."
            )

        merge_preview = self._vcs_service.preview_merge(
            source_ref_or_commit=source_commit,
            target_ref=req.target_ref,
        )

        preview_dict = {
            "can_fast_forward": getattr(merge_preview, "can_fast_forward", False),
            "conflicts": [c.__dict__ if hasattr(c, "__dict__") else c for c in getattr(merge_preview, "conflicts", [])],
            "merge_base_hash": getattr(merge_preview, "merge_base_hash", None),
        }

        gate_c = self._policy.evaluate_gate_c(
            approver=req.approver,
            merge_preview=preview_dict,
        )

        return {
            "eligible": gate_c.decision == GateDecision.PASS,
            "gate_c": gate_c.model_dump(mode="json"),
            "merge_preview": preview_dict,
            "source_commit": source_commit,
            "target_ref": req.target_ref,
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

        candidate, source_commit = self._get_candidate_and_commit(req.experiment_id, req.candidate_id)
        report = self._get_latest_passing_report(req.experiment_id, req.candidate_id)
        if not report or report.get("decision") != GateDecision.PASS.value:
            raise ValueError(
                f"Promotion blocked: Candidate '{req.candidate_id}' has no verified passing Gate B simulation report."
            )

        preview_result = self.preview_promotion(req)
        gate_c = preview_result["gate_c"]
        if gate_c["decision"] != GateDecision.PASS.value and not resolved_config:
            raise ValueError(
                f"Promotion blocked by Gate C checks: "
                f"{'; '.join(c['message'] for c in gate_c['checks'] if c['status'] != 'PASSED')}"
            )

        merge_message = (
            f"Promote candidate '{candidate.get('name', req.candidate_id)}' "
            f"from experiment '{req.experiment_id}' to {req.target_ref}\n\n"
            f"Approver: {req.approver}\n"
            f"Notes: {req.approval_notes or 'None'}"
        )

        merge_result = self._vcs_service.merge(
            source_ref_or_commit=source_commit,
            target_ref=req.target_ref,
            author=req.approver,
            message=merge_message,
            resolved_config=resolved_config,
        )

        merge_commit = getattr(merge_result, "merge_commit_hash", None)
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
                    "source_commit": source_commit,
                    "merge_commit": merge_commit,
                    "target_ref": req.target_ref,
                },
            )

        self.app_logger.info(
            "Successfully promoted candidate %s (experiment %s) to %s at commit %s. Live trading safeguards remain active.",
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
            "status": PromotionLifecycleState.PROMOTED.value,
            "merge_commit_hash": merge_commit,
            "approver": req.approver,
            "live_trading_status": "UNTOUCHED_SAFEGUARDED",
        }

    def _get_candidate_and_commit(self, experiment_id: str, candidate_id: str) -> tuple[dict[str, Any], str]:
        with self._db_manager.get_unit_of_work() as uow:
            exp_repo = uow.get_repository(PostgresExperimentRepository)
            exp = exp_repo.get_experiment(experiment_id)
            if not exp:
                raise ValueError(f"Experiment '{experiment_id}' not found.")

        candidates = (exp.get("spec") or {}).get("candidates", [])
        candidate = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)
        if not candidate:
            raise ValueError(f"Candidate '{candidate_id}' not found in experiment '{experiment_id}'.")

        source_commit = candidate.get("candidate_commit_hash") or exp.get("base_commit_hash")
        if not source_commit:
            raise ValueError(f"Candidate '{candidate_id}' has no committed source hash.")

        return candidate, source_commit

    def _get_latest_passing_report(self, experiment_id: str, candidate_id: str) -> Optional[dict[str, Any]]:
        with self._db_manager.get_unit_of_work() as uow:
            run_repo = uow.get_repository(PostgresSimulatedRunRepository)
            runs = run_repo.list_runs(experiment_id=experiment_id, candidate_id=candidate_id)
            if not runs:
                return None

            report_repo = uow.get_repository(PostgresSimulationReportRepository)
            for run in runs:
                report = report_repo.get_report_by_run(run["run_id"])
                if report and report.get("decision") == GateDecision.PASS.value:
                    return report

        return None
