from __future__ import annotations

import abc
from typing import List, Optional

from database.repositories.base_repository import BaseRepository
from vcs.domain import Reference


class RefRepository(BaseRepository[Reference]):
    @abc.abstractmethod
    def get_by_name(self, name: str, lock_for_update: bool = False) -> Optional[Reference]:
        raise NotImplementedError()

    @abc.abstractmethod
    def set_reference(self, name: str, commit_hash: str) -> Reference:
        raise NotImplementedError()

    @abc.abstractmethod
    def list_all(self) -> List[Reference]:
        raise NotImplementedError()
