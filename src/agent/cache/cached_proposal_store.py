from __future__ import annotations

import threading
from typing import Optional

from cachetools import TTLCache

from src.agent.configuration.models import ConfigurationProposal
from src.core.interfaces.conversation_store import ConversationStore
from src.core.interfaces.proposal_store import ProposalStore


class CachedProposalStore(ProposalStore[ConfigurationProposal]):
    def __init__(
            self,
            conversations: ConversationStore,
            maxsize: int = 1000,
            ttl: int = 3600,
    ):
        self._conversations = conversations
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.RLock()

    def register(self, proposal_id: str, proposal: ConfigurationProposal) -> None:
        with self._lock:
            self._cache[proposal_id] = proposal

    def get(self, proposal_id: str) -> Optional[ConfigurationProposal]:
        with self._lock:
            cached = self._cache.get(proposal_id)
        if cached is not None:
            return cached

        message = self._conversations.get_message(proposal_id)
        if message is None or not message.payload:
            return None

        proposal_data = message.payload.get("proposal", )
        if not proposal_data:
            return None

        proposal = ConfigurationProposal.model_validate(proposal_data)
        with self._lock:
            self._cache[proposal_id] = proposal
        return proposal

    def remove(self, proposal_id: str) -> None:
        with self._lock:
            self._cache.pop(proposal_id, None)
