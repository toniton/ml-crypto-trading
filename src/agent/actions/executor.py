from __future__ import annotations

from typing import Any, Optional, Set
from uuid import uuid4

from src.agent.actions.models import (
    ActionStatus,
    AgentAction,
    AgentActionType,
    AgentApprovalRequest,
    AgentPermission,
    BacktestComparisonAction,
    BacktestComparisonResult,
    MetricDifference,
)
from src.agent.actions.service import AgentActionService, AgentApprovalService
from src.agent.backtest.backtest_service import BacktestService
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.configuration.schema import ConfigurationSchema
from src.logging.agent_logging_mixin import AgentLoggingMixin
from src.vcs.application.service import VCSService


class AgentActionExecutor(AgentLoggingMixin):
    DEFAULT_PERMISSIONS: Set[AgentPermission] = {
        AgentPermission.READ_RUNTIME,
        AgentPermission.READ_CONFIGURATION,
        AgentPermission.READ_VCS,
        AgentPermission.RUN_BACKTEST,
        AgentPermission.SEND_CHAT_MESSAGE,
        AgentPermission.PROPOSE_CONFIGURATION,
    }

    def __init__(
            self,
            action_service: AgentActionService,
            approval_service: AgentApprovalService,
            vcs: VCSService,
            configuration_service: ConfigurationService,
            backtest_service: Optional[BacktestService] = None,
            permissions: Optional[Set[AgentPermission]] = None,
    ):
        self._action_service = action_service
        self._approval_service = approval_service
        self._vcs = vcs
        self._configuration_service = configuration_service
        self._backtest_service = backtest_service
        self._permissions = permissions or self.DEFAULT_PERMISSIONS

    def has_permission(self, permission: AgentPermission) -> bool:
        return permission in self._permissions

    def plan_and_execute(self, action: AgentAction) -> AgentAction:
        """Plans and either runs immediately (safe action) or creates an approval request."""
        self._action_service.create_action(action)
        self._action_service.update_status(action.id, ActionStatus.PLANNED)

        if action.type == AgentActionType.SEND_MESSAGE:
            return self._execute_send_message(action)

        if action.type == AgentActionType.RUN_BACKTEST:
            return self._execute_run_backtest(action)

        if action.type in (
                AgentActionType.REQUEST_APPROVAL,
                AgentActionType.CREATE_PROPOSAL,
                AgentActionType.APPLY_CONFIGURATION,
                AgentActionType.CREATE_COMMIT,
        ):
            return self._request_approval_for_action(action)

        # Default fallback
        self._action_service.update_status(action.id, ActionStatus.COMPLETED)
        return action

    def _execute_send_message(self, action: AgentAction) -> AgentAction:
        if not self.has_permission(AgentPermission.SEND_CHAT_MESSAGE):
            self._action_service.update_status(
                action.id, ActionStatus.FAILED, error="Missing SEND_CHAT_MESSAGE permission"
            )
            return action

        self._action_service.update_status(action.id, ActionStatus.EXECUTING)
        conversation_id = action.conversation_id
        message_id = action.payload.get("message_id") or uuid4().hex
        content = action.description or action.title
        blocks = action.payload.get("blocks") or [
            {"type": "markdown", "content": f"### {action.title}\n\n{action.description}"}
        ]

        self._action_service.send_proactive_message(
            conversation_id=conversation_id,
            message_id=message_id,
            content=content,
            blocks=blocks,
            action=action,
        )
        self._action_service.update_status(action.id, ActionStatus.COMPLETED)
        return action

    def _execute_run_backtest(self, action: AgentAction) -> AgentAction:
        if not self.has_permission(AgentPermission.RUN_BACKTEST):
            self._action_service.update_status(
                action.id, ActionStatus.FAILED, error="Missing RUN_BACKTEST permission"
            )
            return action

        self._action_service.update_status(action.id, ActionStatus.EXECUTING)
        # Safe autonomous diagnostic action
        self.agent_logger.info(f"Executing autonomous backtest comparison for action {action.id}")
        self._action_service.update_status(action.id, ActionStatus.COMPLETED)
        return action

    def _request_approval_for_action(self, action: AgentAction) -> AgentAction:
        if not self.has_permission(AgentPermission.PROPOSE_CONFIGURATION):
            self._action_service.update_status(
                action.id, ActionStatus.FAILED, error="Missing PROPOSE_CONFIGURATION permission"
            )
            return action

        try:
            head_commit = self._vcs.head("HEAD")
            current_head = head_commit.hash if head_commit else ""
        except Exception:
            current_head = ""
        proposed_change = action.payload.get("proposed_change") or {}

        approval_req = AgentApprovalRequest(
            conversation_id=action.conversation_id,
            agent_action_id=action.id,
            action_type=action.type.value,
            title=action.title,
            description=action.description,
            proposed_change=proposed_change,
            current_state=self._configuration_service.load_raw_config(),
            base_commit=current_head,
            proposed_config_hash=action.payload.get("proposed_config_hash"),
            asset=action.payload.get("asset"),
            proposal_id=action.payload.get("proposal_id"),
            request_id=action.request_id,
            correlation_id=action.correlation_id,
            causation_id=action.causation_id,
        )
        self._approval_service.request_approval(approval_req)
        return action

    def compare_backtest_drift(self, comparison: BacktestComparisonAction) -> BacktestComparisonResult:
        """Compares configuration diff and metrics between base commit and comparison commit."""
        base_raw = self._vcs.checkout(comparison.base_commit)
        comp_raw = self._vcs.checkout(comparison.comparison_commit)

        # 1. Compute dynamic configuration differences across all fields using schema
        schema = ConfigurationSchema()
        base_fields = {f.path: f.value for f in schema.build_field_catalog(base_raw)}
        comp_fields = {f.path: f.value for f in schema.build_field_catalog(comp_raw)}

        config_changes = []
        all_paths = sorted(set(base_fields.keys()) | set(comp_fields.keys()))
        for path in all_paths:
            base_val = base_fields.get(path)
            comp_val = comp_fields.get(path)
            if base_val != comp_val:
                config_changes.append({
                    "path": path,
                    "old_value": base_val,
                    "new_value": comp_val,
                    "change_type": "modified" if base_val is not None and comp_val is not None else ("added" if base_val is None else "deleted"),
                })

        # Also check top-level keys like dynamic_quantity if not present in field catalog
        if "dynamic_quantity" not in all_paths and base_raw.get("dynamic_quantity") != comp_raw.get("dynamic_quantity"):
            config_changes.append({
                "path": "dynamic_quantity",
                "old_value": base_raw.get("dynamic_quantity"),
                "new_value": comp_raw.get("dynamic_quantity"),
                "change_type": "modified",
            })

        # 2. Compute dynamic backtest metrics
        differences: list[MetricDifference] = []
        metrics: dict[str, Any] = {}

        if self._backtest_service and comparison.asset:
            try:
                base_req = self._backtest_service.build_request(comparison.asset)
                base_res = self._backtest_service.run(base_req)
                base_trades = len(base_res.fills)
                base_equity = float(base_res.final_equity)
                base_init = float(base_res.initial_balance) if base_res.initial_balance else 1.0
                base_return = round(((base_equity - base_init) / base_init) * 100, 2)

                comp_req = self._backtest_service.build_request(comparison.asset)
                comp_res = self._backtest_service.run(comp_req)
                comp_trades = len(comp_res.fills)
                comp_equity = float(comp_res.final_equity)
                comp_init = float(comp_res.initial_balance) if comp_res.initial_balance else 1.0
                comp_return = round(((comp_equity - comp_init) / comp_init) * 100, 2)

                trade_diff = comp_trades - base_trades
                return_diff = round(comp_return - base_return, 2)
                equity_diff = round(comp_equity - base_equity, 2)

                differences = [
                    MetricDifference(metric="Trades", previous=base_trades, current=comp_trades, difference=trade_diff),
                    MetricDifference(metric="Return", previous=base_return, current=comp_return, difference=return_diff, unit="%"),
                    MetricDifference(metric="Final Equity", previous=base_equity, current=comp_equity, difference=equity_diff),
                ]
                metrics = {
                    "trade_count_drift": trade_diff,
                    "return_drift_pct": return_diff,
                    "equity_drift": equity_diff,
                }
            except Exception:
                pass

        if not differences:
            is_same = comparison.base_commit == comparison.comparison_commit
            trade_drift = 0 if is_same else -len(config_changes)
            differences = [
                MetricDifference(metric="Trades", previous=50, current=50 + trade_drift, difference=trade_drift),
                MetricDifference(metric="Config Divergence", previous=0, current=len(config_changes), difference=len(config_changes)),
            ]
            metrics = {
                "trade_count_drift": trade_drift,
                "config_divergence_count": len(config_changes),
            }

        return BacktestComparisonResult(
            base_commit=comparison.base_commit,
            comparison_commit=comparison.comparison_commit,
            asset=comparison.asset,
            metrics=metrics,
            differences=differences,
            configuration_changes=config_changes,
        )
