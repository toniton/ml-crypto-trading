from installer.context import DatabaseConfig, DatabaseMode, InstallerContext
from installer.steps.database import DatabaseStep


def test_database_step_name():
    step = DatabaseStep()
    assert step.name == "Database Setup & Provisioning"


def test_database_step_run_skips_when_mode_is_skip(tmp_path):
    context = InstallerContext(
        project_root=tmp_path,
        venv_dir=tmp_path / "venv",
        interactive=False,
    )
    context.database.mode = DatabaseMode.SKIP
    step = DatabaseStep()
    assert step.run(context) is True


def test_database_can_connect_socket_returns_false_for_invalid_port():
    step = DatabaseStep()
    assert step._can_connect_socket("127.0.0.1", 65534) is False
