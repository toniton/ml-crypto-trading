from pathlib import Path

from installer.context import InstallerContext
from installer.steps.tenant_bootstrap import TenantBootstrapStep


class TestTenantBootstrapStep:
    def test_defaults_to_default_tenant_when_env_unset(self, monkeypatch, tmp_path: Path):
        monkeypatch.delenv("TENANT_USER_ID", raising=False)
        ctx = InstallerContext(project_root=tmp_path, venv_dir=tmp_path / "venv")
        assert TenantBootstrapStep().run(ctx) is True and ctx.app.tenant_user_id == "default"

    def test_reads_valid_tenant_from_env(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("TENANT_USER_ID", "USR-10492")
        ctx = InstallerContext(project_root=tmp_path, venv_dir=tmp_path / "venv")
        assert TenantBootstrapStep().run(ctx) is True and ctx.app.tenant_user_id == "usr-10492"

    def test_rejects_invalid_tenant_slug(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("TENANT_USER_ID", "admin")
        ctx = InstallerContext(project_root=tmp_path, venv_dir=tmp_path / "venv")
        assert TenantBootstrapStep().run(ctx) is False
