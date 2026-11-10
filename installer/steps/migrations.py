"""Database schema migrations step via Alembic."""

from pathlib import Path
import subprocess

from installer.context import DatabaseMode, InstallerContext
from installer.steps.base import BaseStep
from installer.ui.console import console
from installer.ui.prompts import prompt_confirm
from installer.ui.spinners import task_status


class MigrationsStep(BaseStep):
    """Executes database schema migrations up to head revision."""

    @property
    def name(self) -> str:
        return "Database Schema Migrations"

    def run(self, context: InstallerContext) -> bool:
        console.print_section(self.name)

        if not self._should_run_migrations(context):
            return True

        if context.dry_run:
            console.info("[dry-run] Would execute alembic upgrade head")
            return True

        alembic_bin = self._resolve_alembic_path(context.venv_dir)
        if not alembic_bin.exists():
            console.error(f"Alembic executable not found at {alembic_bin}.")
            return False

        return self._execute_migration(alembic_bin, context.project_root)

    def _should_run_migrations(self, context: InstallerContext) -> bool:
        if context.database.mode == DatabaseMode.SKIP or not context.run_migrations:
            console.info("Skipping database migrations.")
            return False

        if context.interactive:
            context.run_migrations = prompt_confirm(
                "Run database schema migrations now (alembic upgrade head)?",
                default=True,
            )

        if not context.run_migrations:
            console.info("Skipping database migrations by user request.")
            return False

        return True

    def _execute_migration(self, alembic_bin: Path, project_root: Path) -> bool:
        console.info("Applying pending database migrations...")
        try:
            with task_status("Running alembic upgrade head"):
                result = subprocess.run(
                    [str(alembic_bin), "upgrade", "head"],
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    check=False,
                )
            if result.returncode == 0:
                console.success("Database schema is up to date.")
                return True
            console.error(f"Alembic migration failed:\n{result.stderr.strip()}")
            return False
        except (subprocess.SubprocessError, OSError) as exc:
            console.error(f"Could not execute alembic: {exc}")
            return False

    def _resolve_alembic_path(self, venv_dir: Path) -> Path:
        windows_alembic = venv_dir / "Scripts" / "alembic.exe"
        if windows_alembic.exists():
            return windows_alembic
        return venv_dir / "bin" / "alembic"
