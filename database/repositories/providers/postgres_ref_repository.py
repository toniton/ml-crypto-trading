from __future__ import annotations

from typing import List, Optional

from sqlalchemy.dialects.postgresql import insert

from database.dao.reference_dao import ReferenceDao
from database.repositories.ref_repository import RefRepository
from vcs.domain import Reference


class PostgresRefRepository(RefRepository):
    def save(self, entity: Reference) -> Reference:
        return self.set_reference(entity.name, entity.commit_hash)

    def get(self, entity_id: str) -> Optional[Reference]:
        return self.get_by_name(entity_id)

    def get_all(self):
        return self.list_all()

    def update(self, entity_id: str, entity: Reference):
        return self.set_reference(entity_id, entity.commit_hash)

    def upsert(self, entity: Reference) -> None:
        self.set_reference(entity.name, entity.commit_hash)

    def get_by_name(self, name: str, lock_for_update: bool = False) -> Optional[Reference]:
        query = self.database_session.query(ReferenceDao).filter(ReferenceDao.name == name)
        if lock_for_update:
            query = query.with_for_update()
        dao = query.first()
        if not dao:
            return None
        return Reference(name=dao.name, commit_hash=dao.commit_hash, updated_at=dao.updated_at)

    def set_reference(self, name: str, commit_hash: str) -> Reference:
        stmt = insert(ReferenceDao).values(
            name=name,
            commit_hash=commit_hash,
        ).on_conflict_do_update(
            index_elements=["name"],
            set_={"commit_hash": commit_hash}
        )
        self.database_session.execute(stmt)
        dao = self.get_by_name(name)
        assert dao is not None
        return dao

    def list_all(self) -> List[Reference]:
        daos = self.database_session.query(ReferenceDao).all()
        return [Reference(name=d.name, commit_hash=d.commit_hash, updated_at=d.updated_at) for d in daos]
