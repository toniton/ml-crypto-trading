from __future__ import annotations

from typing import Any, List, Optional, Tuple

from src.agent.configuration.configuration_service import ConfigurationService as AgentConfigurationService
from src.agent.configuration.models import ConfigurationProposal, ValidationResult
from src.database.database_manager import DatabaseManager
from src.vcs.application.service import VCSService


class ConfigurationService:
    def __init__(self, db_manager: DatabaseManager, config_filepath: Optional[str] = None):
        self._db_manager = db_manager
        self._config_filepath = config_filepath
        self._vcs = VCSService(db_manager)
        self._delegate = AgentConfigurationService(config_filepath, vcs=self._vcs)

    def validate_proposal(self, proposal: ConfigurationProposal) -> ValidationResult:
        return self._delegate.validate_proposal(proposal)

    def apply_proposal_to_vcs(
            self,
            proposal: ConfigurationProposal,
            author: str = "user",
            ref: str = "HEAD",
    ) -> Tuple[Any, List[str]]:
        return self._delegate.apply_proposal_to_vcs(proposal, author=author, ref=ref)
