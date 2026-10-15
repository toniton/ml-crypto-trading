import pytest

from src.configuration.retention_config import RetentionConfig
from src.retention.models import DataCategory, RetentionMode
from src.retention.policy_resolver import RetentionPolicyResolver


class TestRetentionPolicyResolver:
    def setup_method(self):
        self.config = RetentionConfig()
        self.resolver = RetentionPolicyResolver(self.config)

    def test_builds_policies_for_all_categories(self):
        categories = {policy.data_category for policy in self.resolver.policies()}
        assert DataCategory.TRACE in categories
        assert DataCategory.FINANCIAL in categories
        assert DataCategory.REPORT in categories

    def test_financial_records_are_keep(self):
        policy = self.resolver.get("financial_records")
        assert policy is not None
        assert policy.retention_mode == RetentionMode.KEEP
        assert policy.period_delta() is None

    def test_trace_policy_is_archive_90d(self):
        policy = self.resolver.get("trace_events")
        assert policy is not None
        assert policy.retention_mode == RetentionMode.ARCHIVE
        assert policy.period_delta().days == 90

    def test_market_data_buffer_is_time_based(self):
        policy = self.resolver.get("market_data_buffer")
        assert policy is not None
        assert policy.data_category == DataCategory.MARKET_DATA_BUFFER
        assert policy.retention_mode == RetentionMode.DELETE
        assert policy.period_delta().total_seconds() == 6 * 3600

    def test_unknown_category_raises(self):
        with pytest.raises(ValueError):
            RetentionPolicyResolver._resolve_category("mystery", "NOT_A_CATEGORY")

    def test_version_changes_after_update(self):
        before = self.resolver.version
        old, new = self.resolver.update("trace_events", retention_period="30d")
        assert self.resolver.version != before
        assert old["retention_period"] == "90d"
        assert new["retention_period"] == "30d"

    def test_update_rejects_invalid_duration(self):
        with pytest.raises(ValueError):
            self.resolver.update("trace_events", retention_period="soon")

    def test_requires_confirmation_for_shorter_retention(self):
        old = self.resolver.get("trace_events").to_dict()
        candidate = {**old, "retention_period": "30d"}
        assert RetentionPolicyResolver.requires_confirmation(old, candidate) is True

    def test_requires_confirmation_when_enabling_destructive_mode(self):
        old = {"retention_mode": "ARCHIVE", "retention_period": "90d", "enabled": True}
        new = {"retention_mode": "DELETE", "retention_period": "90d", "enabled": True}
        assert RetentionPolicyResolver.requires_confirmation(old, new) is True

    def test_no_confirmation_for_lengthening_retention(self):
        old = self.resolver.get("trace_events").to_dict()
        candidate = {**old, "retention_period": "365d"}
        assert RetentionPolicyResolver.requires_confirmation(old, candidate) is False

    def test_category_from_key_when_omitted(self):
        assert RetentionPolicyResolver._resolve_category("trace_events", None) == DataCategory.TRACE
        assert RetentionPolicyResolver._resolve_category("TRACE", None) == DataCategory.TRACE

    def test_policy_settings_validates_duration(self):
        from src.configuration.retention_config import PolicySettings
        with pytest.raises(ValueError):
            PolicySettings(retention_period="not_a_duration")

    def test_default_experiment_artifacts_mode_is_delete(self):
        from src.configuration.retention_config import default_policies
        defaults = default_policies()
        assert defaults["experiment_artifacts"].retention_mode == RetentionMode.DELETE
