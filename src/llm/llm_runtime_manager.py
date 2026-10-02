from __future__ import annotations

import threading
from typing import Dict, List, Optional

from langchain_core.tools import BaseTool

from src.configuration.llm_config import LlmConfig
from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.llm_adapter import LlmAdapter
from src.database.repositories.providers.postgres_llm_credential_repository import (
    PostgresLlmCredentialRepository,
)
from src.entities.llm_credential import LlmCredential
from src.llm.dynamic_llm_adapter import DynamicLlmAdapter
from src.llm.model_factory import ModelFactory
from src.llm.tools.tool_factory import ToolFactory
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class LlmRuntimeManager(ApplicationLoggingMixin):
    """Manages available LLM models from llm.yaml and enables runtime model switching."""

    def __init__(
            self,
            llm_config: LlmConfig,
            db_manager: DatabaseManager,
            tool_map: Optional[Dict[str, BaseTool]] = None,
    ):
        self._llm_config = llm_config
        self._db_manager = db_manager
        self._tool_map: Dict[str, BaseTool] = tool_map or {}
        self._lock = threading.RLock()
        self._bound_tools: List[BaseTool] = []
        self._active_model_id: str = ""
        self._active_adapter: Optional[LlmAdapter] = None
        self._proxy_adapter = DynamicLlmAdapter(self)

        # Initialize active model
        self.rebuild_active_adapter()

    @property
    def proxy_adapter(self) -> LlmAdapter:
        return self._proxy_adapter

    @property
    def active_model_id(self) -> str:
        with self._lock:
            return self._active_model_id

    def set_bound_tools(self, tools: List[BaseTool]) -> None:
        with self._lock:
            self._bound_tools = tools
            if self._active_adapter is not None:
                self._active_adapter.bind_tools(tools)

    def update_tool_map(self, tool_map: Dict[str, BaseTool]) -> None:
        with self._lock:
            self._tool_map = tool_map
            enabled_tools = ToolFactory.get_enabled_tools(tool_map, self._llm_config)
            self.set_bound_tools(enabled_tools)

    def get_active_adapter(self) -> LlmAdapter:
        with self._lock:
            if self._active_adapter is None:
                self.rebuild_active_adapter()
            assert self._active_adapter is not None
            return self._active_adapter

    def resolve_active_model_id(self) -> str:
        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresLlmCredentialRepository)
                active = repo.get_active()
                if isinstance(active, LlmCredential) and isinstance(active.model_id, str):
                    for model in self._llm_config.models:
                        if active.model_id in (model.id, model.name):
                            return active.model_id
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.debug(f"Could not read active model from DB: {exc}")

        return self._llm_config.default_model.model_id

    def rebuild_active_adapter(self) -> LlmAdapter:
        with self._lock:
            model_id = self.resolve_active_model_id()
            model_config = self._llm_config.get_model(model_id)

            api_key = None
            api_base_url = None
            try:
                with self._db_manager.get_unit_of_work() as uow:
                    repo = uow.get_repository(PostgresLlmCredentialRepository)
                    cred = repo.get_by_model_id(model_id)
                    if isinstance(cred, LlmCredential):
                        api_key = cred.api_key
                        api_base_url = cred.api_base_url
            except Exception as exc:  # pylint: disable=broad-except
                self.app_logger.debug(f"Could not read credentials for '{model_id}' from DB: {exc}")

            adapter = ModelFactory.create_model(
                self._llm_config,
                model_name=model_config.name,
            )

            # Bind enabled tools
            tools_to_bind = self._bound_tools or ToolFactory.get_enabled_tools(
                self._tool_map, self._llm_config
            )
            if tools_to_bind:
                adapter.bind_tools(tools_to_bind)

            self._active_model_id = model_id
            self._active_adapter = adapter
            self.app_logger.info(
                f"Active LLM model set to '{model_id}' ({model_config.name} / {model_config.provider.value})"
            )
            return adapter

    def switch_active_model(self, model_id: str) -> dict:
        with self._lock:
            model_config = self._llm_config.get_model(model_id)

            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresLlmCredentialRepository)
                cred = repo.get_by_model_id(model_id)
                if not cred:
                    repo.save_credential(
                        model_id=model_id,
                        provider=model_config.provider.value,
                        is_active=True,
                    )
                else:
                    repo.set_active(model_id)

            self.rebuild_active_adapter()
            return {
                "active_model_id": model_id,
                "name": model_config.name,
                "provider": model_config.provider.value,
                "status": "ready",
            }

    def save_credential(
            self,
            model_id: str,
            api_key: Optional[str] = None,
            api_base_url: Optional[str] = None,
    ) -> LlmCredential:
        with self._lock:
            model_config = self._llm_config.get_model(model_id)
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresLlmCredentialRepository)
                updated = repo.save_credential(
                    model_id=model_id,
                    provider=model_config.provider.value,
                    api_key=api_key,
                    api_base_url=api_base_url,
                )

            # If the saved credential is for the active model, refresh the adapter
            if self._active_model_id == model_id:
                self.rebuild_active_adapter()

            return updated

    def delete_credential(self, model_id: str) -> bool:
        with self._lock:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresLlmCredentialRepository)
                return repo.delete_by_model_id(model_id)

    def list_models_status(self) -> List[dict]:
        active_id = self.resolve_active_model_id()
        cred_map: Dict[str, LlmCredential] = {}
        try:
            with self._db_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresLlmCredentialRepository)
                for cred in repo.get_all():
                    cred_map[cred.model_id] = cred
        except Exception:  # pylint: disable=broad-except
            pass

        result = []
        for model in self._llm_config.models:
            mid = model.model_id
            cred = cred_map.get(mid)
            has_db_key = bool(cred and cred.api_key)
            masked_key = (
                f"••••••••{cred.api_key[-4:]}"
                if (cred and cred.api_key and len(cred.api_key) > 4)
                else ("••••••••" if has_db_key else None)
            )

            result.append({
                "id": mid,
                "name": model.name,
                "provider": model.provider.value,
                "model_name": model.model_name,
                "api_base_url": (cred.api_base_url if cred and cred.api_base_url else model.api_base_url),
                "temperature": model.temperature,
                "timeout": model.timeout,
                "capabilities": model.capabilities,
                "requires_api_key": model.requires_api_key,
                "has_api_key": has_db_key,
                "masked_api_key": masked_key,
                "is_active": (mid == active_id),
                "is_default": model.default,
            })
        return result

    def list_tools_status(self) -> List[dict]:
        return [
            {
                "name": tool.name,
                "enabled": tool.enabled,
                "category": tool.category,
                "description": tool.description,
            }
            for tool in self._llm_config.tools.bot_tools
        ]
