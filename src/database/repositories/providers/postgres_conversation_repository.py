from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from src.core.interfaces.llm_adapter import ChatTurn
from src.database.dao.conversation_dao import ConversationDao
from src.database.dao.conversation_message_dao import ConversationMessageDao
from src.database.repositories.conversation_repository import ConversationRepository


class PostgresConversationRepository(ConversationRepository):
    def save(self, entity: ChatTurn) -> ChatTurn:
        raise NotImplementedError("Use append() to persist conversation turns.")

    def get(self, entity_id: str) -> Optional[ChatTurn]:
        raise NotImplementedError("Conversation turns are addressed by session id; use get_history().")

    def get_all(self) -> List[ChatTurn]:
        raise NotImplementedError("Conversation turns are addressed by session id; use get_history().")

    def update(self, entity_id: str, entity: ChatTurn):
        raise NotImplementedError("Conversation turns are immutable.")

    def upsert(self, entity: ChatTurn) -> None:
        raise NotImplementedError("Use append() to persist conversation turns.")

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

    def append(self, session_id: str, turn: ChatTurn, max_turns: int) -> None:
        self.database_session.add(
            ConversationMessageDao(
                conversation_id=session_id,
                role=turn.role,
                content=turn.content,
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
