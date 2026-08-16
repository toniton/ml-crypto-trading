from __future__ import annotations

import abc
from typing import Optional

from src.database.repositories.base_repository import BaseRepository
from src.vcs.domain import Blob


class BlobRepository(BaseRepository[Blob]):
    @abc.abstractmethod
    def get_by_hash(self, blob_hash: str) -> Optional[Blob]:
        raise NotImplementedError()

    @abc.abstractmethod
    def save_blob(self, blob: Blob) -> Blob:
        raise NotImplementedError()

    @abc.abstractmethod
    def exists(self, blob_hash: str) -> bool:
        raise NotImplementedError()
