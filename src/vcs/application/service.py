from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel

from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_blob_repository import PostgresBlobRepository
from src.database.repositories.providers.postgres_commit_repository import PostgresCommitRepository
from src.database.repositories.providers.postgres_ref_repository import PostgresRefRepository
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.vcs.application.semantic_merge import SemanticMergeEngine
from src.vcs.core.hashing import Hashing
from src.vcs.core.serializer import Serializer
from src.vcs.domain import (
    Blob,
    BlobNotFoundError,
    Commit,
    CommitNotFoundError,
    InvalidReferenceError,
    MergePreview,
    MergeResult,
    MergeStatus,
    Reference,
    VcsError,
)


class VCSService(ApplicationLoggingMixin):
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def resolve_commit_hash(self, commit_hash_or_ref: str) -> str:
        with self.db_manager.get_unit_of_work() as uow:
            ref_repo = uow.get_repository(PostgresRefRepository)

            # 1. Build candidates list in priority order
            candidates = [commit_hash_or_ref]
            if commit_hash_or_ref in ("refs/heads/main", "main", "HEAD"):
                for alias in ("refs/heads/main", "main", "HEAD"):
                    if alias not in candidates:
                        candidates.append(alias)
            elif commit_hash_or_ref.startswith("refs/heads/"):
                short_name = commit_hash_or_ref[len("refs/heads/"):]
                candidates.append(short_name)
            else:
                candidates.append(f"refs/heads/{commit_hash_or_ref}")
                if not commit_hash_or_ref.startswith("backtest/"):
                    candidates.append(f"refs/heads/backtest/{commit_hash_or_ref}")

            for cand in candidates:
                ref_obj = ref_repo.get_by_name(cand)
                if ref_obj:
                    return ref_obj.commit_hash

            # 2. Check if it's a direct commit hash
            commit_repo = uow.get_repository(PostgresCommitRepository)
            commit_obj = commit_repo.get_by_hash(commit_hash_or_ref)
            if commit_obj:
                return commit_obj.hash

        raise InvalidReferenceError(f"Could not resolve '{commit_hash_or_ref}' to a valid commit or reference.")

    def head(self, ref: str = "HEAD") -> Commit:
        commit_hash = self.resolve_commit_hash(ref)
        with self.db_manager.get_unit_of_work() as uow:
            commit_repo = uow.get_repository(PostgresCommitRepository)
            commit = commit_repo.get_by_hash(commit_hash)
            if not commit:
                raise CommitNotFoundError(commit_hash)
            return commit

    def get_blob(self, commit_hash_or_ref: str) -> Blob:
        commit_hash = self.resolve_commit_hash(commit_hash_or_ref)
        with self.db_manager.get_unit_of_work() as uow:
            commit_repo = uow.get_repository(PostgresCommitRepository)
            blob_repo = uow.get_repository(PostgresBlobRepository)

            commit = commit_repo.get_by_hash(commit_hash)
            if not commit:
                raise CommitNotFoundError(commit_hash)

            blob = blob_repo.get_by_hash(commit.blob_hash)
            if not blob:
                raise BlobNotFoundError(commit.blob_hash)

            self.app_logger.debug(f"Checked out blob for commit {commit_hash[:8]}")
            return blob

    def checkout(self, commit_hash_or_ref: str) -> Dict[str, Any]:
        blob = self.get_blob(commit_hash_or_ref)
        return blob.content

    def commit(
            self,
            content: Union[BaseModel, Dict[str, Any]],
            author: str,
            message: str,
            ref: str = "HEAD",
            metadata: Optional[Dict[str, Any]] = None,
    ) -> Commit:
        if metadata is None:
            metadata = {}

        canonical_dict = Serializer.to_canonical_dict(content)
        blob_hash = Hashing.compute_blob_hash(canonical_dict)
        now = datetime.now(timezone.utc)

        with self.db_manager.get_unit_of_work() as uow:
            ref_repo = uow.get_repository(PostgresRefRepository)
            commit_repo = uow.get_repository(PostgresCommitRepository)
            blob_repo = uow.get_repository(PostgresBlobRepository)

            # Row lock on the reference pointer to guarantee atomicity and prevent concurrent lost updates
            existing_ref = ref_repo.get_by_name(ref, lock_for_update=True)
            if not existing_ref and ref in ("HEAD", "refs/heads/main", "main"):
                for alias in ("HEAD", "refs/heads/main", "main"):
                    if found := ref_repo.get_by_name(alias, lock_for_update=True):
                        existing_ref = found
                        break
            parent_hash = existing_ref.commit_hash if existing_ref else None

            # 1. Save blob (deduplicated)
            blob = Blob(hash=blob_hash, content=canonical_dict, created_at=now)
            blob_repo.save_blob(blob)

            # 2. Compute deterministic commit hash & save commit
            commit_hash = Hashing.compute_commit_hash(
                blob_hash=blob_hash,
                parent_hash=parent_hash,
                author=author,
                message=message,
                metadata=metadata,
                timestamp=now,
            )
            commit_obj = Commit(
                hash=commit_hash,
                blob_hash=blob_hash,
                parent_hash=parent_hash,
                author=author,
                message=message,
                metadata=metadata,
                created_at=now,
            )
            commit_repo.save_commit(commit_obj)

            # 3. Move reference pointer (and sync aliases if HEAD/main)
            ref_repo.set_reference(ref, commit_hash)
            if ref in ("HEAD", "refs/heads/main", "main"):
                ref_repo.set_reference("HEAD", commit_hash)
                ref_repo.set_reference("refs/heads/main", commit_hash)

            self.app_logger.info(f"Committed snapshot {commit_hash[:8]} to ref '{ref}' by {author}")
            return commit_obj

    def seed_if_empty(
            self,
            content: Union[BaseModel, Dict[str, Any]],
            author: str,
            message: str,
            ref: str = "HEAD",
    ) -> Optional[Commit]:
        with self.db_manager.get_unit_of_work() as uow:
            ref_repo = uow.get_repository(PostgresRefRepository)
            existing_ref = ref_repo.get_by_name(ref)
            if not existing_ref and ref in ("HEAD", "refs/heads/main", "main"):
                for alias in ("HEAD", "refs/heads/main", "main"):
                    if found := ref_repo.get_by_name(alias):
                        existing_ref = found
                        break
            if existing_ref:
                self.app_logger.info("Config store already seeded for ref '%s'", ref)
                if ref in ("HEAD", "refs/heads/main", "main"):
                    ref_repo.set_reference("HEAD", existing_ref.commit_hash)
                    ref_repo.set_reference("refs/heads/main", existing_ref.commit_hash)
                return None
        return self.commit(content, author=author, message=message, ref=ref)

    def reset(self, ref: str, commit_hash_or_ref: str) -> Reference:
        target_commit_hash = self.resolve_commit_hash(commit_hash_or_ref)
        with self.db_manager.get_unit_of_work() as uow:
            ref_repo = uow.get_repository(PostgresRefRepository)
            ref_repo.get_by_name(ref, lock_for_update=True)

            ref_result = ref_repo.set_reference(ref, target_commit_hash)
            self.app_logger.info(f"Reset ref '{ref}' pointer to {target_commit_hash[:8]}")
            return ref_result

    def branch(self, name: str, from_ref: str = "HEAD") -> Reference:
        target_commit_hash = self.resolve_commit_hash(from_ref)
        with self.db_manager.get_unit_of_work() as uow:
            ref_repo = uow.get_repository(PostgresRefRepository)
            ref_result = ref_repo.set_reference(name, target_commit_hash)
            self.app_logger.info(f"Created branch '{name}' pointing to {target_commit_hash[:8]}")
            return ref_result

    def log(self, ref: str = "HEAD", limit: int = 100) -> List[Commit]:
        start_commit_hash = self.resolve_commit_hash(ref)
        with self.db_manager.get_unit_of_work() as uow:
            commit_repo = uow.get_repository(PostgresCommitRepository)
            return commit_repo.get_log(start_commit_hash, limit=limit)

    def list_branches(self, prefix: str = "refs/heads/") -> List[Reference]:
        with self.db_manager.get_unit_of_work() as uow:
            ref_repo = uow.get_repository(PostgresRefRepository)
            refs = ref_repo.list_all()
            return [r for r in refs if r.name.startswith(prefix) or r.name in ("HEAD", "main")]

    def delete_branch(self, name: str) -> bool:
        if name in ("HEAD", "refs/heads/main", "main"):
            raise VcsError(f"Cannot delete protected branch '{name}'")
        with self.db_manager.get_unit_of_work() as uow:
            ref_repo = uow.get_repository(PostgresRefRepository)
            return ref_repo.delete_reference(name)

    def find_merge_base(self, commit_a: str, commit_b: str) -> Optional[str]:
        hash_a = self.resolve_commit_hash(commit_a)
        hash_b = self.resolve_commit_hash(commit_b)

        if hash_a == hash_b:
            return hash_a

        with self.db_manager.get_unit_of_work() as uow:
            commit_repo = uow.get_repository(PostgresCommitRepository)

            # Traverse ancestors of A
            ancestors_a: Dict[str, int] = {}
            queue = [(hash_a, 0)]
            visited = set()

            while queue:
                current_h, depth = queue.pop(0)
                if current_h in visited:
                    continue
                visited.add(current_h)
                ancestors_a[current_h] = depth

                c = commit_repo.get_by_hash(current_h)
                if not c:
                    continue
                if c.parent_hash:
                    queue.append((c.parent_hash, depth + 1))
                if parents := c.metadata.get("parents"):
                    for p in parents:
                        queue.append((p, depth + 1))

            # Traverse ancestors of B and find first match
            queue_b = [(hash_b, 0)]
            visited_b = set()
            candidates = []

            while queue_b:
                current_h, depth = queue_b.pop(0)
                if current_h in visited_b:
                    continue
                visited_b.add(current_h)

                if current_h in ancestors_a:
                    candidates.append((ancestors_a[current_h] + depth, current_h))

                c = commit_repo.get_by_hash(current_h)
                if not c:
                    continue
                if c.parent_hash:
                    queue_b.append((c.parent_hash, depth + 1))
                if parents := c.metadata.get("parents"):
                    for p in parents:
                        queue_b.append((p, depth + 1))

            if candidates:
                candidates.sort(key=lambda x: x[0])
                return candidates[0][1]

        return None

    def preview_merge(
        self,
        source_ref_or_commit: str,
        target_ref: str = "refs/heads/main",
    ) -> MergePreview:
        source_hash = self.resolve_commit_hash(source_ref_or_commit)
        try:
            target_hash = self.resolve_commit_hash(target_ref)
        except InvalidReferenceError:
            target_hash = self.resolve_commit_hash("HEAD")

        merge_base = self.find_merge_base(target_hash, source_hash)
        if not merge_base:
            merge_base = target_hash

        can_fast_forward = (merge_base == target_hash)

        if source_hash == target_hash:
            return MergePreview(
                status=MergeStatus.CLEAN,
                merge_base_hash=merge_base,
                target_head_hash=target_hash,
                source_commit_hash=source_hash,
                can_fast_forward=True,
                conflicts=[],
                merged_config=self.checkout(source_hash),
            )

        base_config = self.checkout(merge_base)
        ours_config = self.checkout(target_hash)
        theirs_config = self.checkout(source_hash)

        merged_config, conflicts = SemanticMergeEngine.merge(base_config, ours_config, theirs_config)

        # Validate merged configuration structure
        validation_errors: List[str] = []
        try:
            from src.configuration.trading_config import TradingConfig
            TradingConfig.model_validate(merged_config)
        except Exception as exc:
            validation_errors.append(str(exc))

        status = MergeStatus.FAST_FORWARD if can_fast_forward and not conflicts else (
            MergeStatus.CONFLICT if conflicts else MergeStatus.CLEAN
        )

        return MergePreview(
            status=status,
            merge_base_hash=merge_base,
            target_head_hash=target_hash,
            source_commit_hash=source_hash,
            can_fast_forward=can_fast_forward,
            conflicts=conflicts,
            merged_config=merged_config,
            validation_errors=validation_errors,
        )

    def merge(
        self,
        source_ref_or_commit: str,
        target_ref: str = "refs/heads/main",
        author: str = "user",
        message: Optional[str] = None,
        expected_target_head: Optional[str] = None,
        resolved_config: Optional[Dict[str, Any]] = None,
    ) -> MergeResult:
        source_hash = self.resolve_commit_hash(source_ref_or_commit)
        target_hash = self.resolve_commit_hash(target_ref)

        if expected_target_head and target_hash != expected_target_head:
            raise VcsError(
                f"Target HEAD changed since merge preview: expected {expected_target_head[:8]}, actual is {target_hash[:8]}."
            )

        final_config: Dict[str, Any]
        if resolved_config is not None:
            final_config = resolved_config
        else:
            preview = self.preview_merge(source_ref_or_commit, target_ref)
            if preview.conflicts:
                raise VcsError(
                    f"Cannot auto-merge with {len(preview.conflicts)} unresolved conflicts."
                )
            if not preview.merged_config:
                raise VcsError("Merged configuration is empty.")
            final_config = preview.merged_config

        # Validate final config with Pydantic
        from src.configuration.trading_config import TradingConfig
        validated = TradingConfig.model_validate(final_config)

        canonical_dict = Serializer.to_canonical_dict(validated)
        blob_hash = Hashing.compute_blob_hash(canonical_dict)
        now = datetime.now(timezone.utc)

        merge_msg = message or f"Merge '{source_ref_or_commit}' into {target_ref}"
        metadata = {
            "parents": [target_hash, source_hash],
            "merge_source": source_ref_or_commit,
            "merge_target": target_ref,
        }

        with self.db_manager.get_unit_of_work() as uow:
            ref_repo = uow.get_repository(PostgresRefRepository)
            commit_repo = uow.get_repository(PostgresCommitRepository)
            blob_repo = uow.get_repository(PostgresBlobRepository)

            # Optimistic lock on target ref
            existing_ref = ref_repo.get_by_name(target_ref, lock_for_update=True)
            if not existing_ref and target_ref in ("refs/heads/main", "main", "HEAD"):
                for alias in ("refs/heads/main", "main", "HEAD"):
                    if found := ref_repo.get_by_name(alias, lock_for_update=True):
                        existing_ref = found
                        break
            if existing_ref and existing_ref.commit_hash != target_hash:
                raise VcsError("Target branch was updated concurrently.")

            # Save blob
            blob = Blob(hash=blob_hash, content=canonical_dict, created_at=now)
            blob_repo.save_blob(blob)

            # Compute merge commit hash & save
            commit_hash = Hashing.compute_commit_hash(
                blob_hash=blob_hash,
                parent_hash=target_hash,
                author=author,
                message=merge_msg,
                metadata=metadata,
                timestamp=now,
            )
            commit_obj = Commit(
                hash=commit_hash,
                blob_hash=blob_hash,
                parent_hash=target_hash,
                author=author,
                message=merge_msg,
                metadata=metadata,
                created_at=now,
            )
            commit_repo.save_commit(commit_obj)

            # Update target ref and HEAD/main aliases
            ref_repo.set_reference(target_ref, commit_hash)
            if target_ref in ("refs/heads/main", "main", "HEAD"):
                ref_repo.set_reference("HEAD", commit_hash)
                ref_repo.set_reference("refs/heads/main", commit_hash)

            self.app_logger.info(
                f"Successfully created merge commit {commit_hash[:8]} on '{target_ref}'"
            )

            return MergeResult(
                merge_commit_hash=commit_hash,
                target_ref=target_ref,
                source_commit_hash=source_hash,
                status="MERGED",
                message=merge_msg,
                parents=[target_hash, source_hash],
            )

