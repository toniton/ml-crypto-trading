import sys
from installer.context import InstallerContext
from installer.steps.preflight import PreflightStep


def test_preflight_step_name():
    step = PreflightStep()
    assert step.name == "System & Environment Preflight Check"


def test_preflight_check_python_version_succeeds_on_current_runtime():
    step = PreflightStep()
    assert step._check_python_version() is True


def test_preflight_check_python_version_fails_on_old_version(monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 10, 0))
    step = PreflightStep()
    assert step._check_python_version() is False


def test_preflight_detect_os_returns_string():
    step = PreflightStep()
    assert isinstance(step._detect_os(), str)


def test_preflight_step_run_returns_true(tmp_path):
    context = InstallerContext(project_root=tmp_path, venv_dir=tmp_path / "venv")
    step = PreflightStep()
    assert step.run(context) is True
