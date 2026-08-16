from __future__ import annotations

from typing import List, Optional

from src.database.dao.commit_dao import CommitDao
from src.database.repositories.commit_repository import CommitRepository
from src.vcs.domain import Commit


class PostgresCommitRepository(CommitRepository):
    def save(self, entity: Commit) -> Commit:
        return self.save_commit(entity)

    def get(self, entity_id: str) -> Optional[Commit]:
        return self.get_by_hash(entity_id)

    def get_all(self) -> List[Commit]:
        commits = self.database_session.query(CommitDao).all()
        return [
            Commit(
                hash=d.hash,
                blob_hash=d.blob_hash,
                parent_hash=d.parent_hash,
                author=d.author,
                message=d.message,
                metadata=d.metadata_ or {},
                created_at=d.created_at,
            )
            for d in commits
        ]

    def update(self, entity_id: str, entity: Commit):
        raise NotImplementedError("Commits are immutable.")

    def upsert(self, entity: Commit) -> None:
        self.save_commit(entity)

    def get_by_hash(self, commit_hash: str) -> Optional[Commit]:
        dao = self.database_session.query(CommitDao).filter(CommitDao.hash == commit_hash).first()
        if not dao:
            return None
        return Commit(
            hash=dao.hash,
            blob_hash=dao.blob_hash,
            parent_hash=dao.parent_hash,
            author=dao.author,
            message=dao.message,
            metadata=dao.metadata_ or {},
            created_at=dao.created_at,
        )

    def save_commit(self, commit: Commit) -> Commit:
        commit_dao = CommitDao(
            hash=commit.hash,
            blob_hash=commit.blob_hash,
            parent_hash=commit.parent_hash,
            author=commit.author,
            message=commit.message,
            metadata_=commit.metadata,
            created_at=commit.created_at,
        )
        self.database_session.add(commit_dao)
        return commit

    def get_log(self, start_commit_hash: str, limit: int = 100) -> List[Commit]:
        history: List[Commit] = []
        current_hash: Optional[str] = start_commit_hash

        while current_hash and len(history) < limit:
            commit = self.get_by_hash(current_hash)
            if not commit:
                break
            history.append(commit)
            current_hash = commit.parent_hash

        return history
