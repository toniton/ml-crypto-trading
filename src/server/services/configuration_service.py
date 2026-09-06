from __future__ import annotations

from typing import Any, List, Optional, Tuple

from api.interfaces.timeframe import Timeframe
from api.interfaces.asset_schedule import AssetSchedule
from src.agent.configuration.configuration_service import ConfigurationService as AgentConfigurationService
from src.agent.configuration.models import ConfigurationProposal, ValidationResult
from src.configuration.trading_config import TradingConfig
from src.database.database_manager import DatabaseManager
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.vcs.application.service import VCSService
from src.vcs.domain.exceptions import CommitNotFoundError, InvalidReferenceError


class ConfigurationService:
    def __init__(self, db_manager: DatabaseManager, config_filepath: Optional[str] = None):
        self._db_manager = db_manager
        self._config_filepath = config_filepath
        self._vcs = VCSService(db_manager)
        self._delegate = AgentConfigurationService(config_filepath, vcs=self._vcs)

    def get_config(self) -> dict:
        raw = self._delegate.load_raw_config()
        commit_hash = None
        try:
            head_commit = self._vcs.head("HEAD")
            commit_hash = head_commit.hash
        except (CommitNotFoundError, InvalidReferenceError):
            pass
        return {
            "assets": raw.get("assets", []),
            "dynamic_quantity": raw.get("dynamic_quantity"),
            "commit_hash": commit_hash,
        }

    @classmethod
    def get_options(cls) -> dict:
        return {
            "exchanges": [
                exchange_provider.value for exchange_provider in ExchangeProvidersEnum
            ],
            "timeframes": [
                candle_timeframe.value for candle_timeframe in Timeframe
            ],
            "schedules": [
                {
                    "value": asset_schedule.value,
                    "label": asset_schedule.name.replace("_", " ").title(),
                }
                for asset_schedule in AssetSchedule
            ],
        }

    def commit_config(
            self,
            config_data: dict,
            author: str = "user",
            message: str = "Update bot configuration",
            ref: str = "HEAD",
    ) -> Any:
        validated_config = TradingConfig.model_validate(config_data)
        return self._vcs.commit(
            validated_config,
            author=author,
            message=message,
            ref=ref,
        )

    def validate_proposal(self, proposal: ConfigurationProposal) -> ValidationResult:
        return self._delegate.validate_proposal(proposal)

    def apply_proposal_to_vcs(
            self,
            proposal: ConfigurationProposal,
            author: str = "user",
            ref: str = "HEAD",
    ) -> Tuple[Any, List[str]]:
        return self._delegate.apply_proposal_to_vcs(proposal, author=author, ref=ref)

