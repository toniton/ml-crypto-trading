from unittest.mock import patch
from pathlib import Path
from installer.context import InstallerContext
from installer.steps.verification import VerificationStep


def test_verification_step_name():
    step = VerificationStep()
    assert step.name == "Installation Verification & Quickstart Summary"


def test_verification_step_run_in_dry_run_returns_true(tmp_path):
    context = InstallerContext(
        project_root=tmp_path,
        venv_dir=tmp_path / "venv",
        dry_run=True,
        interactive=False,
    )
    step = VerificationStep()
    assert step.run(context) is True


def test_verification_start_bot_passes_assets_conf(tmp_path):
    context = InstallerContext(project_root=tmp_path, venv_dir=tmp_path / "venv", interactive=False)
    step = VerificationStep()
    with patch("subprocess.run") as mock_run:
        step._start_bot(context)
        expected_config = str(tmp_path / "examples" / "configurations" / "trading-config.yaml")
        assert f"--assets-conf={expected_config}" in mock_run.call_args[0][0]


def test_verification_start_bot_passes_simulated_flag(tmp_path):
    context = InstallerContext(project_root=tmp_path, venv_dir=tmp_path / "venv", interactive=False)
    step = VerificationStep()
    with patch("subprocess.run") as mock_run:
        step._start_bot(context)
        assert "--simulated=true" in mock_run.call_args[0][0]
