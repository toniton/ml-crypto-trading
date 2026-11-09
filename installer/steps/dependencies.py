"""Python virtual environment and package dependencies installation step."""

from pathlib import Path
import subprocess
import sys

from installer.context import InstallerContext
from installer.steps.base import BaseStep
from installer.ui.console import console
from installer.ui.spinners import task_status


class DependenciesStep(BaseStep):
    """Creates virtual environment and installs project dependencies via pip."""

    @property
    def name(self) -> str:
        return "Python Environment & Dependencies Setup"

    def run(self, context: InstallerContext) -> bool:
        console.print_section(self.name)

        if context.dry_run:
            console.info(f"[dry-run] Would prepare venv at {context.venv_dir} and install packages")
            return True

        self._ensure_virtualenv(context.venv_dir)

        pip_bin = self._resolve_pip_path(context.venv_dir)
        python_bin = self._resolve_python_path(context.venv_dir)

        console.info(f"Using virtual environment Python: {python_bin}")

        req_file = (
            context.project_root / "requirements-dev.txt"
            if context.install_dev_deps
            else context.project_root / "requirements.txt"
        )

        if not req_file.exists():
            console.warning(f"Requirements file not found at {req_file}")
            return True

        console.info(f"Installing dependencies from {req_file.name}...")
        try:
            with task_status("Installing packages with pip"):
                result = subprocess.run(
                    [str(pip_bin), "install", "-r", str(req_file)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            if result.returncode == 0:
                console.success("Dependencies installed successfully.")
                return True
            console.warning("Pip reported warnings/errors during installation.")
            return True
        except (subprocess.SubprocessError, OSError) as exc:
            console.error(f"Failed to run pip: {exc}")
            return False

    def _ensure_virtualenv(self, venv_dir: Path) -> None:
        if venv_dir.exists() and (venv_dir / "pyvenv.cfg").exists():
            console.info(f"Existing virtual environment found at {venv_dir}")
            return

        console.info(f"Creating virtual environment at {venv_dir}...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        console.success("Virtual environment created.")

    def _resolve_pip_path(self, venv_dir: Path) -> Path:
        windows_pip = venv_dir / "Scripts" / "pip.exe"
        if windows_pip.exists():
            return windows_pip
        return venv_dir / "bin" / "pip"

    def _resolve_python_path(self, venv_dir: Path) -> Path:
        windows_python = venv_dir / "Scripts" / "python.exe"
        if windows_python.exists():
            return windows_python
        return venv_dir / "bin" / "python3"
