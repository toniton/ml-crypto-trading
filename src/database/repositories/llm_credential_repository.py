from __future__ import annotations

import abc
from typing import List, Optional

from src.database.repositories.base_repository import BaseRepository
from src.entities.llm_credential import LlmCredential


class LlmCredentialRepository(BaseRepository[LlmCredential]):
    @abc.abstractmethod
    def get_by_model_id(self, model_id: str) -> Optional[LlmCredential]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_by_provider(self, provider: str) -> List[LlmCredential]:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_active(self) -> Optional[LlmCredential]:
        raise NotImplementedError()

    @abc.abstractmethod
    def set_active(self, model_id: str) -> LlmCredential:
        raise NotImplementedError()

    @abc.abstractmethod
    def save_credential(
            self,
            model_id: str,
            provider: str,
            api_key: Optional[str] = None,
            api_base_url: Optional[str] = None,
            is_active: Optional[bool] = None,
    ) -> LlmCredential:
        raise NotImplementedError()

    @abc.abstractmethod
    def delete_by_model_id(self, model_id: str) -> bool:
        raise NotImplementedError()
