import unittest
from unittest.mock import MagicMock

from src.database.dao.llm_credential_dao import LlmCredentialDao
from src.database.repositories.providers.postgres_llm_credential_repository import (
    PostgresLlmCredentialRepository,
)


class TestPostgresLlmCredentialRepository(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.repo = PostgresLlmCredentialRepository(database_session=self.session)

    def test_save_new_credential(self):
        self.session.query.return_value.filter.return_value.first.return_value = None

        cred = self.repo.save_credential(
            model_id="groq-qwen",
            provider="groq",
            api_key="gsk-12345",
            api_base_url="https://api.groq.com",
            is_active=True,
        )

        self.session.add.assert_called_once()
        self.session.flush.assert_called_once()
        self.assertEqual(cred.model_id, "groq-qwen")
        self.assertEqual(cred.provider, "groq")
        self.assertEqual(cred.api_key, "gsk-12345")
        self.assertTrue(cred.is_active)

    def test_update_existing_credential(self):
        dao = LlmCredentialDao(
            id=1,
            model_id="gemini-3-flash",
            provider="gemini",
            api_key="old-key",
            api_base_url=None,
            is_active=False,
        )
        self.session.query.return_value.filter.return_value.first.return_value = dao

        cred = self.repo.save_credential(
            model_id="gemini-3-flash",
            provider="gemini",
            api_key="new-key",
        )

        self.assertEqual(dao.api_key, "new-key")
        self.assertEqual(cred.api_key, "new-key")

    def test_set_active_switches_active_flag(self):
        dao = LlmCredentialDao(
            id=2,
            model_id="deepseek-chat",
            provider="deepseek",
            api_key="sk-123",
            is_active=False,
        )
        self.session.query.return_value.filter.return_value.first.return_value = dao

        cred = self.repo.set_active("deepseek-chat")

        self.session.execute.assert_called_once()
        self.assertTrue(dao.is_active)
        self.assertEqual(cred.model_id, "deepseek-chat")

    def test_set_active_raises_when_model_not_found(self):
        self.session.query.return_value.filter.return_value.first.return_value = None

        with self.assertRaises(ValueError):
            self.repo.set_active("non-existent")

    def test_get_active(self):
        dao = LlmCredentialDao(
            id=3,
            model_id="groq-qwen",
            provider="groq",
            is_active=True,
        )
        self.session.query.return_value.filter.return_value.first.return_value = dao

        active = self.repo.get_active()
        self.assertIsNotNone(active)
        self.assertEqual(active.model_id, "groq-qwen")
        self.assertTrue(active.is_active)

    def test_delete_by_model_id(self):
        self.session.query.return_value.filter.return_value.delete.return_value = 1
        deleted = self.repo.delete_by_model_id("groq-qwen")
        self.assertTrue(deleted)


if __name__ == "__main__":
    unittest.main()
