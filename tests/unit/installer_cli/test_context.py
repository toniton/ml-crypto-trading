from pathlib import Path
import pytest
from installer.context import (
    DatabaseConfig,
    DatabaseMode,
    InstallProfile,
    InstallerContext,
)


def test_database_config_host_with_port():
    config = DatabaseConfig(host="db.example.com", port=5433)
    assert config.host_with_port == "db.example.com:5433"


def test_installer_context_env_file_path(tmp_path):
    context = InstallerContext(project_root=tmp_path, venv_dir=tmp_path / "venv")
    assert context.env_file_path == tmp_path / ".env"


def test_installer_context_env_example_path(tmp_path):
    context = InstallerContext(project_root=tmp_path, venv_dir=tmp_path / "venv")
    assert context.env_example_path == tmp_path / ".env.example"


def test_installer_context_default_profile(tmp_path):
    context = InstallerContext(project_root=tmp_path, venv_dir=tmp_path / "venv")
    assert context.profile == InstallProfile.QUICKSTART


def test_installer_context_default_database_mode(tmp_path):
    context = InstallerContext(project_root=tmp_path, venv_dir=tmp_path / "venv")
    assert context.database.mode == DatabaseMode.DOCKER
