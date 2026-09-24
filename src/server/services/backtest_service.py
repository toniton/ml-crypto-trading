from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.configuration.trading_config import TradingConfig
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_backtest_repository import PostgresBacktestRepository
from src.database.repositories.providers.postgres_commit_repository import PostgresCommitRepository
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.vcs.application.service import VCSService
from src.vcs.domain.exceptions import CommitNotFoundError, InvalidReferenceError
from src.vcs.domain.merge import MergePreview, MergeResult


class BacktestService(ApplicationLoggingMixin):
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.vcs = VCSService(db_manager)

    @staticmethod
    def _sanitize_branch_id(name: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_-]", "-", name.strip().lower())
        clean = re.sub(r"-+", "-", clean).strip("-")
        return clean or f"bt-{uuid.uuid4().hex[:8]}"

    def create_branch(
            self,
            name: str,
            description: Optional[str] = None,
            source_commit_hash: Optional[str] = None,
            author: str = "user",
    ) -> Dict[str, Any]:
        source_hash = source_commit_hash
        if not source_hash:
            try:
                head_commit = self.vcs.head("refs/heads/main")
                source_hash = head_commit.hash
            except (CommitNotFoundError, InvalidReferenceError):
                head_commit = self.vcs.head("HEAD")
                source_hash = head_commit.hash

        branch_slug = self._sanitize_branch_id(name)
        branch_id = f"bt-{branch_slug[:32]}-{uuid.uuid4().hex[:4]}"
        ref_name = f"refs/heads/backtest/{branch_id}"

        # Point branch ref to source commit
        self.vcs.branch(ref_name, from_ref=source_hash)

        return {
            "branch_id": branch_id,
            "ref_name": ref_name,
            "name": name,
            "description": description or "",
            "author": author,
            "source_commit_hash": source_hash,
            "head_commit_hash": source_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def list_branches(self) -> List[Dict[str, Any]]:
        refs = self.vcs.list_branches(prefix="refs/heads/backtest/")
        results: List[Dict[str, Any]] = []

        with self.db_manager.get_unit_of_work() as uow:
            backtest_repo = uow.get_repository(PostgresBacktestRepository)
            commit_repo = uow.get_repository(PostgresCommitRepository)
            all_sessions = backtest_repo.list_sessions(limit=200)

            for ref in refs:
                if not ref.name.startswith("refs/heads/backtest/"):
                    continue

                branch_id = ref.name.replace("refs/heads/backtest/", "")
                head_commit = commit_repo.get_by_hash(ref.commit_hash)

                # Find runs associated with this branch
                branch_runs = [
                    s for s in all_sessions
                    if s.config and s.config.get("branch_id") == branch_id
                ]

                latest_run_metrics = None
                if branch_runs:
                    latest_run = branch_runs[0]
                    latest_run_metrics = backtest_repo.get_result_metrics(latest_run.id)

                results.append({
                    "branch_id": branch_id,
                    "ref_name": ref.name,
                    "name": branch_id.replace("bt-", "").replace("-", " ").title(),
                    "head_commit_hash": ref.commit_hash,
                    "head_commit_message": head_commit.message if head_commit else None,
                    "parent_hash": head_commit.parent_hash if head_commit else None,
                    "updated_at": ref.updated_at.isoformat() if ref.updated_at else None,
                    "total_runs": len(branch_runs),
                    "latest_run_metrics": latest_run_metrics,
                })

        return results

    def get_branch(self, branch_id: str) -> Dict[str, Any]:
        ref_name = f"refs/heads/backtest/{branch_id}"
        head_commit = self.vcs.head(ref_name)

        commits = self.vcs.log(ref=ref_name, limit=50)

        with self.db_manager.get_unit_of_work() as uow:
            backtest_repo = uow.get_repository(PostgresBacktestRepository)
            all_sessions = backtest_repo.list_sessions(limit=200)
            branch_runs = [
                {
                    "session_id": s.id,
                    "ticker_symbol": s.ticker_symbol,
                    "status": s.status.value,
                    "commit_hash": s.config.get("commit_hash") if s.config else None,
                    "initial_balance": s.config.get("initial_balance") if s.config else None,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "metrics": backtest_repo.get_result_metrics(s.id),
                }
                for s in all_sessions
                if s.config and s.config.get("branch_id") == branch_id
            ]

        return {
            "branch_id": branch_id,
            "ref_name": ref_name,
            "name": branch_id.replace("bt-", "").replace("-", " ").title(),
            "head_commit": {
                "hash": head_commit.hash,
                "blob_hash": head_commit.blob_hash,
                "parent_hash": head_commit.parent_hash,
                "author": head_commit.author,
                "message": head_commit.message,
                "created_at": head_commit.created_at.isoformat() if head_commit.created_at else None,
            },
            "commits": [
                {
                    "hash": c.hash,
                    "parent_hash": c.parent_hash,
                    "author": c.author,
                    "message": c.message,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "parents": c.metadata.get("parents", [c.parent_hash] if c.parent_hash else []),
                }
                for c in commits
            ],
            "runs": branch_runs,
        }

    def delete_branch(self, branch_id: str) -> bool:
        ref_name = f"refs/heads/backtest/{branch_id}"
        return self.vcs.delete_branch(ref_name)

    def get_configuration(
            self,
            branch_id: str,
            commit_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        ref_or_hash = commit_hash or f"refs/heads/backtest/{branch_id}"
        config_dict = self.vcs.checkout(ref_or_hash)
        active_commit = self.vcs.head(ref_or_hash)

        return {
            "branch_id": branch_id,
            "commit_hash": active_commit.hash,
            "assets": config_dict.get("assets", []),
            "dynamic_quantity": config_dict.get("dynamic_quantity"),
        }

    @staticmethod
    def _merge_asset_data(
            assets: List[Dict[str, Any]],
            asset_symbol: str,
            asset_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        merged_assets: List[Dict[str, Any]] = copy.deepcopy(assets)
        norm_target = asset_symbol.replace("/", "_").upper()
        found_idx = -1
        for idx, a in enumerate(merged_assets):
            base = str(a.get("base_ticker_symbol", "")).upper()
            quote = str(a.get("quote_ticker_symbol", "")).upper()
            pair = f"{base}_{quote}"
            if pair == norm_target or a.get("name", "").upper() == norm_target:
                found_idx = idx
                break

        if found_idx >= 0:
            merged_assets[found_idx] = {**merged_assets[found_idx], **asset_data}
        else:
            merged_assets.append(asset_data)
        return merged_assets

    def update_asset_configuration(
            self,
            branch_id: str,
            asset_symbol: str,
            asset_data: Dict[str, Any],
            author: str = "user",
            message: Optional[str] = None,
    ) -> Dict[str, Any]:
        ref_name = f"refs/heads/backtest/{branch_id}"
        current_config = self.vcs.checkout(ref_name)
        assets = self._merge_asset_data(current_config.get("assets", []), asset_symbol, asset_data)

        updated_dict = {
            **current_config,
            "assets": assets,
        }

        # Validate with TradingConfig
        validated = TradingConfig.model_validate(updated_dict)

        commit_msg = message or f"Update {asset_symbol} configuration on {branch_id}"
        commit_obj = self.vcs.commit(
            validated,
            author=author,
            message=commit_msg,
            ref=ref_name,
            metadata={"branch_id": branch_id, "asset": asset_symbol},
        )

        created_at: Optional[datetime] = commit_obj.created_at
        created_at_str = (
            created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)  # pylint: disable=no-member
        )
        return {
            "branch_id": branch_id,
            "commit_hash": commit_obj.hash,
            "message": commit_obj.message,
            "created_at": created_at_str,
        }

    def preview_merge(
            self,
            branch_id: str,
            commit_hash: Optional[str] = None,
            target_ref: str = "refs/heads/main",
    ) -> MergePreview:
        source = commit_hash or f"refs/heads/backtest/{branch_id}"
        return self.vcs.preview_merge(source, target_ref=target_ref)

    def execute_merge(
            self,
            branch_id: str,
            commit_hash: Optional[str] = None,
            target_ref: str = "refs/heads/main",
            author: str = "user",
            message: Optional[str] = None,
            expected_target_head: Optional[str] = None,
            resolved_config: Optional[Dict[str, Any]] = None,
    ) -> MergeResult:
        ref_name = f"refs/heads/backtest/{branch_id}"
        source = commit_hash if commit_hash else ref_name
        return self.vcs.merge(
            source_ref_or_commit=source,
            target_ref=target_ref,
            author=author,
            message=message or f"Merge backtest '{branch_id}' into {target_ref}",
            expected_target_head=expected_target_head,
            resolved_config=resolved_config,
        )
