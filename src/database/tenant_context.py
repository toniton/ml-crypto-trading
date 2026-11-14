from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
import os
from typing import Iterator, Optional

from sqlalchemy import Column, String
from sqlalchemy.orm import declared_attr


class TenantContext:
    DEFAULT_TENANT_ID = "default"
    TENANT_ENV_VAR = "TENANT_USER_ID"
    _tenant_id_var: ContextVar[Optional[str]] = ContextVar("tenant_user_id", default=None)

    @classmethod
    def get_current_tenant_id(cls) -> str:
        scoped = cls._tenant_id_var.get()
        if scoped:
            return scoped
        env_tenant = os.getenv(cls.TENANT_ENV_VAR, "").strip()
        return env_tenant or cls.DEFAULT_TENANT_ID

    @classmethod
    def set_tenant_context(cls, tenant_id: Optional[str]) -> Token[Optional[str]]:
        normalized = tenant_id.strip() if tenant_id else None
        return cls._tenant_id_var.set(normalized)

    @classmethod
    def reset_tenant_context(cls, token: Token[Optional[str]]) -> None:
        cls._tenant_id_var.reset(token)

    @classmethod
    @contextmanager
    def scope(cls, tenant_id: Optional[str]) -> Iterator[str]:
        token = cls.set_tenant_context(tenant_id)
        try:
            yield cls.get_current_tenant_id()
        finally:
            cls.reset_tenant_context(token)


class TenantScopedMixin:
    @declared_attr
    def user_id(cls):  # pylint: disable=no-self-argument
        return Column(
            String(64),
            nullable=False,
            default=TenantContext.get_current_tenant_id,
            server_default=TenantContext.DEFAULT_TENANT_ID,
            index=True,
        )
