from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from src.core.interfaces.conversation_store import ConversationMessage, SessionSummary
from src.core.interfaces.llm_adapter import ChatTurn
from src.database.dao.conversation_dao import ConversationDao
from src.database.dao.conversation_message_dao import ConversationMessageDao
from src.database.repositories.conversation_repository import ConversationRepository


class PostgresConversationRepository(ConversationRepository):
    def save(self, entity: ConversationMessage) -> ConversationMessage:
        raise NotImplementedError("Use append() to persist conversation messages.")

    def get(self, entity_id: str) -> Optional[ConversationMessage]:
        raise NotImplementedError("Conversation messages are addressed by session id; use get_messages().")

    def get_all(self) -> List[ConversationMessage]:
        raise NotImplementedError("Conversation messages are addressed by session id; use get_messages().")

    def update(self, entity_id: str, entity: ConversationMessage):
        raise NotImplementedError("Conversation messages are immutable.")

    def upsert(self, entity: ConversationMessage) -> None:
        raise NotImplementedError("Use append() to persist conversation messages.")

    def get_or_create(self, session_id: str) -> str:
        stmt = insert(ConversationDao).values(id=session_id).on_conflict_do_nothing(index_elements=["id"])
        self.database_session.execute(stmt)
        return session_id

    def get_history(self, session_id: str, limit: int) -> List[ChatTurn]:
        rows = (
            self.database_session.query(ConversationMessageDao)
            .filter(ConversationMessageDao.conversation_id == session_id)
            .order_by(ConversationMessageDao.id.desc())
            .limit(limit)
            .all()
        )
        return [ChatTurn(role=row.role, content=row.content) for row in reversed(rows)]

    def get_messages(self, session_id: str) -> List[ConversationMessage]:
        rows = (
            self.database_session.query(ConversationMessageDao)
            .filter(ConversationMessageDao.conversation_id == session_id)
            .order_by(ConversationMessageDao.id.asc())
            .all()
        )
        return [self._to_message(row) for row in rows]

    def get_by_message_id(self, message_id: str) -> Optional[ConversationMessage]:
        row = (
            self.database_session.query(ConversationMessageDao)
            .filter(
                ConversationMessageDao.message_id == message_id,
                ConversationMessageDao.role == "assistant",
            )
            .order_by(ConversationMessageDao.id.desc())
            .first()
        )
        return self._to_message(row) if row else None

    def list_sessions(self) -> List[SessionSummary]:
        message_count = func.count(ConversationMessageDao.id).label("message_count")  # pylint: disable=not-callable
        rows = (
            self.database_session.query(ConversationDao, message_count)
            .outerjoin(ConversationMessageDao, ConversationMessageDao.conversation_id == ConversationDao.id)
            .group_by(ConversationDao.id)
            .order_by(ConversationDao.updated_at.desc())
            .all()
        )
        return [
            SessionSummary(
                id=conversation.id,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                message_count=count,
            )
            for conversation, count in rows
        ]

    def append(self, session_id: str, message: ConversationMessage, max_turns: int) -> None:
        self.database_session.add(
            ConversationMessageDao(
                conversation_id=session_id,
                role=message.role,
                content=message.content,
                message_id=message.message_id or None,
                payload=message.payload,
            )
        )
        self.database_session.flush()
        self._prune(session_id, max_turns)
        self.database_session.query(ConversationDao).filter(ConversationDao.id == session_id).update(
            {"updated_at": func.now()}  # pylint: disable=not-callable
        )

    def _prune(self, session_id: str, max_turns: int) -> None:
        keep_ids = [
            row.id
            for row in (
                self.database_session.query(ConversationMessageDao.id)
                .filter(ConversationMessageDao.conversation_id == session_id)
                .order_by(ConversationMessageDao.id.desc())
                .limit(max_turns)
                .all()
            )
        ]
        if not keep_ids:
            return
        self.database_session.query(ConversationMessageDao).filter(
            ConversationMessageDao.conversation_id == session_id,
            ConversationMessageDao.id.notin_(keep_ids),
        ).delete(synchronize_session=False)

    @staticmethod
    def _to_message(row: ConversationMessageDao) -> ConversationMessage:
        return ConversationMessage(
            id=row.id,
            message_id=row.message_id or "",
            role=row.role,
            content=row.content,
            payload=row.payload,
            created_at=row.created_at,
            conversation_id=row.conversation_id,
        )
