from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel

from database.database_manager import DatabaseManager
from database.repositories.providers.postgres_blob_repository import PostgresBlobRepository
from database.repositories.providers.postgres_commit_repository import PostgresCommitRepository
from database.repositories.providers.postgres_ref_repository import PostgresRefRepository
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from vcs.core.hashing import Hashing
from vcs.core.serializer import Serializer
from vcs.domain import (Blob, BlobNotFoundError, Commit, CommitNotFoundError, InvalidReferenceError, Reference)


class VCSService(ApplicationLoggingMixin):
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def resolve_commit_hash(self, commit_hash_or_ref: str) -> str:
        with self.db_manager.get_unit_of_work() as uow:
            ref_repo = uow.get_repository(PostgresRefRepository)
            ref_obj = ref_repo.get_by_name(commit_hash_or_ref)
            if ref_obj:
                return ref_obj.commit_hash

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

            # 3. Move reference pointer
            ref_repo.set_reference(ref, commit_hash)

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
            if existing_ref:
                self.app_logger.info("Config store already seeded for ref '%s'", ref)
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
