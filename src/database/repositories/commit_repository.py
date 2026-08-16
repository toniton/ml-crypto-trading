from __future__ import annotations

import abc
from typing import List, Optional

from src.database.repositories.base_repository import BaseRepository
from src.vcs.domain import Commit


class CommitRepository(BaseRepository[Commit]):
    @abc.abstractmethod
    def get_by_hash(self, commit_hash: str) -> Optional[Commit]:
        raise NotImplementedError()

    @abc.abstractmethod
    def save_commit(self, commit: Commit) -> Commit:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_log(self, start_commit_hash: str, limit: int = 100) -> List[Commit]:
        raise NotImplementedError()
