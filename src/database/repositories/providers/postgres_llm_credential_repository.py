from __future__ import annotations

from typing import List, Optional

from sqlalchemy import update

from src.database.dao.llm_credential_dao import LlmCredentialDao
from src.database.repositories.llm_credential_repository import LlmCredentialRepository
from src.entities.llm_credential import LlmCredential


class PostgresLlmCredentialRepository(LlmCredentialRepository):
    @staticmethod
    def _dao_to_entity(dao: LlmCredentialDao) -> LlmCredential:
        return LlmCredential(
            id=dao.id,
            model_id=dao.model_id,
            provider=dao.provider,
            api_key=dao.api_key,
            api_base_url=dao.api_base_url,
            is_active=dao.is_active,
            created_timestamp=dao.created_timestamp,
            last_updated_timestamp=dao.last_updated_timestamp,
        )

    def save(self, entity: LlmCredential) -> LlmCredential:
        return self.save_credential(
            model_id=entity.model_id,
            provider=entity.provider,
            api_key=entity.api_key,
            api_base_url=entity.api_base_url,
            is_active=entity.is_active,
        )

    def get(self, entity_id: str) -> Optional[LlmCredential]:
        return self.get_by_model_id(entity_id)

    def get_all(self) -> List[LlmCredential]:
        daos = self.database_session.query(LlmCredentialDao).all()
        return [self._dao_to_entity(dao) for dao in daos]

    def update(self, entity_id: str, entity: LlmCredential) -> LlmCredential:
        return self.save_credential(
            model_id=entity_id,
            provider=entity.provider,
            api_key=entity.api_key,
            api_base_url=entity.api_base_url,
            is_active=entity.is_active,
        )

    def upsert(self, entity: LlmCredential) -> None:
        self.save(entity)

    def get_by_model_id(self, model_id: str) -> Optional[LlmCredential]:
        dao = (
            self.database_session.query(LlmCredentialDao)
            .filter(LlmCredentialDao.model_id == model_id)
            .first()
        )
        return self._dao_to_entity(dao) if dao else None

    def get_by_provider(self, provider: str) -> List[LlmCredential]:
        daos = (
            self.database_session.query(LlmCredentialDao)
            .filter(LlmCredentialDao.provider == provider)
            .all()
        )
        return [self._dao_to_entity(dao) for dao in daos]

    def get_active(self) -> Optional[LlmCredential]:
        dao = (
            self.database_session.query(LlmCredentialDao)
            .filter(LlmCredentialDao.is_active.is_(True))
            .first()
        )
        return self._dao_to_entity(dao) if dao else None

    def set_active(self, model_id: str) -> LlmCredential:
        dao = (
            self.database_session.query(LlmCredentialDao)
            .filter(LlmCredentialDao.model_id == model_id)
            .first()
        )
        if not dao:
            raise ValueError(f"Model '{model_id}' not found in credentials store.")

        # Deactivate all active models
        self.database_session.execute(
            update(LlmCredentialDao)
            .where(LlmCredentialDao.is_active.is_(True))
            .values(is_active=False)
        )
        # Activate the selected model
        dao.is_active = True
        self.database_session.flush()
        return self._dao_to_entity(dao)

    def save_credential(
            self,
            model_id: str,
            provider: str,
            api_key: Optional[str] = None,
            api_base_url: Optional[str] = None,
            is_active: Optional[bool] = None,
    ) -> LlmCredential:
        dao = (
            self.database_session.query(LlmCredentialDao)
            .filter(LlmCredentialDao.model_id == model_id)
            .first()
        )
        if is_active is True:
            self.database_session.execute(
                update(LlmCredentialDao)
                .where(LlmCredentialDao.is_active.is_(True))
                .values(is_active=False)
            )

        if not dao:
            dao = LlmCredentialDao(
                model_id=model_id,
                provider=provider,
                api_key=api_key,
                api_base_url=api_base_url,
                is_active=bool(is_active),
            )
            self.database_session.add(dao)
        else:
            dao.provider = provider
            if api_key is not None:
                dao.api_key = api_key
            if api_base_url is not None:
                dao.api_base_url = api_base_url
            if is_active is not None:
                dao.is_active = is_active

        self.database_session.flush()
        return self._dao_to_entity(dao)

    def delete_by_model_id(self, model_id: str) -> bool:
        count = (
            self.database_session.query(LlmCredentialDao)
            .filter(LlmCredentialDao.model_id == model_id)
            .delete()
        )
        self.database_session.flush()
        return count > 0
