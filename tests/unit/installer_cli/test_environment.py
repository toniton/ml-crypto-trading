from installer.context import InstallerContext
from installer.steps.environment import EnvironmentStep


def test_environment_step_name():
    step = EnvironmentStep()
    assert step.name == "Environment File (.env) Configuration"


def test_environment_step_creates_env_if_missing(tmp_path):
    context = InstallerContext(
        project_root=tmp_path,
        venv_dir=tmp_path / "venv",
        interactive=False,
    )
    step = EnvironmentStep()
    step.run(context)
    assert (tmp_path / ".env").exists()


def test_environment_step_creates_backup_when_env_exists(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OLD_KEY=old_value\n", encoding="utf-8")
    context = InstallerContext(
        project_root=tmp_path,
        venv_dir=tmp_path / "venv",
        interactive=False,
    )
    step = EnvironmentStep()
    step.run(context)
    backups = list(tmp_path.glob(".env.backup.*"))
    assert len(backups) == 1


def test_environment_step_updates_existing_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=old_value\n", encoding="utf-8")
    context = InstallerContext(
        project_root=tmp_path,
        venv_dir=tmp_path / "venv",
        interactive=False,
    )
    context.app.app_env = "staging"
    step = EnvironmentStep()
    step.run(context)
    assert "APP_ENV=staging" in env_file.read_text(encoding="utf-8")


def test_environment_step_appends_new_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=1\n", encoding="utf-8")
    context = InstallerContext(
        project_root=tmp_path,
        venv_dir=tmp_path / "venv",
        interactive=False,
    )
    context.credentials.crypto_dot_com_key = "test_key_123"
    step = EnvironmentStep()
    step.run(context)
    assert "CRYPTO_DOT_COM__API_KEY=test_key_123" in env_file.read_text(encoding="utf-8")


def test_environment_step_dry_run_leaves_file_untouched(tmp_path):
    context = InstallerContext(
        project_root=tmp_path,
        venv_dir=tmp_path / "venv",
        dry_run=True,
        interactive=False,
    )
    step = EnvironmentStep()
    step.run(context)
    assert not (tmp_path / ".env").exists()


def test_environment_step_handles_backslashes_in_secrets(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("CRYPTO_DOT_COM__SECRET_KEY=placeholder\n", encoding="utf-8")
    context = InstallerContext(
        project_root=tmp_path,
        venv_dir=tmp_path / "venv",
        interactive=False,
    )
    context.credentials.crypto_dot_com_secret = r"secret\1\g<test>"
    step = EnvironmentStep()
    step.run(context)
    assert r"CRYPTO_DOT_COM__SECRET_KEY=secret\1\g<test>" in env_file.read_text(encoding="utf-8")
