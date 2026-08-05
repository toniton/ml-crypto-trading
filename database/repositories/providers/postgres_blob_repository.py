from __future__ import annotations

from typing import List, Optional

from sqlalchemy.dialects.postgresql import insert

from database.dao.blob_dao import BlobDao
from database.repositories.blob_repository import BlobRepository
from vcs.domain import Blob


class PostgresBlobRepository(BlobRepository):
    def save(self, entity: Blob) -> Blob:
        return self.save_blob(entity)

    def get(self, entity_id: str) -> Optional[Blob]:
        return self.get_by_hash(entity_id)

    def get_all(self) -> List[Blob]:
        blobs = self.database_session.query(BlobDao).all()
        return [Blob(hash=d.hash, content=d.content, created_at=d.created_at) for d in blobs]

    def update(self, entity_id: str, entity: Blob):
        raise NotImplementedError("Blobs are immutable.")

    def upsert(self, entity: Blob) -> None:
        self.save_blob(entity)

    def get_by_hash(self, blob_hash: str) -> Optional[Blob]:
        dao = self.database_session.query(BlobDao).filter(BlobDao.hash == blob_hash).first()
        if not dao:
            return None
        return Blob(hash=dao.hash, content=dao.content, created_at=dao.created_at)

    def save_blob(self, blob: Blob) -> Blob:
        stmt = insert(BlobDao).values(
            hash=blob.hash,
            content=blob.content,
            created_at=blob.created_at,
        ).on_conflict_do_nothing(index_elements=["hash"])
        self.database_session.execute(stmt)
        return blob

    def exists(self, blob_hash: str) -> bool:
        return self.database_session.query(BlobDao.hash).filter(BlobDao.hash == blob_hash).first() is not None
