"""Post-installation verification and quickstart summary step."""

from pathlib import Path
import subprocess

from installer.context import DatabaseMode, InstallerContext
from installer.steps.base import BaseStep
from installer.ui.console import console
from installer.ui.prompts import prompt_confirm


class VerificationStep(BaseStep):
    """Verifies that the installed environment functions correctly and prints next steps."""

    @property
    def name(self) -> str:
        return "Installation Verification & Quickstart Summary"

    def run(self, context: InstallerContext) -> bool:
        console.print_section(self.name)

        if not context.dry_run:
            self._verify_python_imports(context)

        self._print_summary(context)

        if context.interactive:
            launch = prompt_confirm("Start MCT Trading Bot in paper-trading / simulation mode now?", default=False)
            if launch:
                self._start_bot(context)

        return True

    def _verify_python_imports(self, context: InstallerContext) -> None:
        python_bin = self._resolve_python_path(context.venv_dir)
        if not python_bin.exists():
            return

        cmd = [str(python_bin), "-c", "import fastapi, pydantic, sqlalchemy; print('Core modules verified.')"]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(context.project_root),
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                console.success("Core runtime dependencies verified successfully.")
            else:
                console.warning("Core dependencies check returned a non-zero code.")
        except OSError:
            pass

    def _print_summary(self, context: InstallerContext) -> None:
        console.print_banner(
            "Installation Complete!",
            "MCT Trading Bot backend is ready for use.",
        )
        console.info("Quickstart Commands:")
        console.info("  source venv/bin/activate       # Activate virtual environment")
        console.info("  make run-simulated             # Start in simulated paper-trading mode")
        console.info("  make run-live                  # Start in live trading mode with API server")
        console.info("  make test                      # Run unit test suite")
        console.info("  make db-up / make db-down      # Manage PostgreSQL container")

    def _start_bot(self, context: InstallerContext) -> None:
        python_bin = self._resolve_python_path(context.venv_dir)
        config_path = context.project_root / "examples" / "configurations" / "trading-config.yaml"
        cmd = [
            str(python_bin),
            "main.py",
            f"--assets-conf={config_path}",
            "--simulated=true",
        ]
        console.info(f"Starting bot in simulated mode: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, cwd=str(context.project_root), check=False)
        except KeyboardInterrupt:
            console.info("\nBot stopped by user.")

    def _resolve_python_path(self, venv_dir: Path) -> Path:
        windows_python = venv_dir / "Scripts" / "python.exe"
        if windows_python.exists():
            return windows_python
        return venv_dir / "bin" / "python3"
