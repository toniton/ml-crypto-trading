import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.llm.tools.configuration_history_tool import ConfigurationHistoryTool
from src.vcs.application.service import VCSService
from src.vcs.domain import Commit


class TestConfigurationHistoryTool(unittest.TestCase):
    def _commit(self, hash_, author, message):
        return Commit(
            hash=hash_,
            blob_hash="blob",
            parent_hash=None,
            author=author,
            message=message,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    def test_formats_commits(self):
        vcs = MagicMock(spec=VCSService)
        vcs.log.return_value = [
            self._commit("a" * 64, "toni", "Increase buy threshold"),
            self._commit("b" * 64, "bootstrap", "Initial config"),
        ]
        tool = ConfigurationHistoryTool(vcs=vcs)
        result = tool._run(limit=10)
        self.assertIn("Configuration history", result)
        self.assertIn("toni", result)
        self.assertIn("Increase buy threshold", result)
        vcs.log.assert_called_once_with("HEAD", limit=10)

    def test_empty_history(self):
        vcs = MagicMock(spec=VCSService)
        vcs.log.return_value = []
        tool = ConfigurationHistoryTool(vcs=vcs)
        self.assertIn("No configuration history", tool._run())

    def test_error_propagated(self):
        vcs = MagicMock(spec=VCSService)
        vcs.log.side_effect = RuntimeError("boom")
        tool = ConfigurationHistoryTool(vcs=vcs)
        self.assertIn("boom", tool._run())
