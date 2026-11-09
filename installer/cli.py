"""Command line interface orchestration for the installer."""

import argparse
from pathlib import Path
import sys
from typing import List

from installer.context import DatabaseMode, InstallProfile, InstallerContext
from installer.steps import (
    BaseStep,
    CredentialsStep,
    DatabaseStep,
    DependenciesStep,
    EnvironmentStep,
    MigrationsStep,
    PreflightStep,
    VerificationStep,
)
from installer.ui.console import console
from installer.ui.prompts import prompt_choice


def create_argument_parser() -> argparse.ArgumentParser:
    """Constructs the command-line arguments parser."""
    parser = argparse.ArgumentParser(
        prog="python -m installer",
        description="MCT Trading Bot Backend CLI Installer",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without interactive prompts using defaults and flags",
    )
    parser.add_argument(
        "--profile",
        type=str,
        choices=[p.value for p in InstallProfile],
        default=InstallProfile.QUICKSTART.value,
        help="Installation profile (default: quickstart)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the installation without writing files or running external commands",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip pip dependency installation",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip database provisioning and connection checks",
    )
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Skip running Alembic database migrations",
    )
    parser.add_argument(
        "--venv-dir",
        type=Path,
        default=None,
        help="Custom path to the Python virtual environment directory",
    )
    return parser


def apply_profile_defaults(context: InstallerContext) -> None:
    """Applies profile-specific defaults to the installation context."""
    if context.profile == InstallProfile.DEVELOPER:
        context.install_dev_deps = True
        context.app.app_env = "staging"
    elif context.profile == InstallProfile.PRODUCTION:
        context.install_dev_deps = False
        context.app.app_env = "production"
    elif context.profile == InstallProfile.QUICKSTART:
        context.install_dev_deps = False
        context.app.app_env = "production"


def build_pipeline(skip_deps: bool) -> List[BaseStep]:
    """Assembles the sequence of installation steps based on flags."""
    steps: List[BaseStep] = [
        PreflightStep(),
        DatabaseStep(),
        CredentialsStep(),
        EnvironmentStep(),
    ]

    if not skip_deps:
        steps.append(DependenciesStep())

    steps.append(MigrationsStep())
    steps.append(VerificationStep())
    return steps


def main(argv: List[str] = None) -> int:
    """Main CLI entrypoint."""
    parser = create_argument_parser()
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parent.parent
    venv_dir = args.venv_dir or (project_root / "venv")

    context = InstallerContext(
        project_root=project_root,
        venv_dir=venv_dir,
        profile=InstallProfile(args.profile),
        interactive=not args.non_interactive,
        dry_run=args.dry_run,
        run_migrations=not args.skip_migrations,
    )

    if args.skip_db:
        context.database.mode = DatabaseMode.SKIP

    console.print_banner(
        "MCT Trading Bot - Backend Interactive Installer",
        "Configures environment, database, credentials, and dependencies.",
    )

    if context.interactive:
        profile_choices = [
            (InstallProfile.QUICKSTART.value, "Quickstart (Docker DB + Simulated Trading defaults)"),
            (InstallProfile.DEVELOPER.value, "Developer Setup (Dev tools, tests, pre-commit hooks)"),
            (InstallProfile.PRODUCTION.value, "Production Setup (Custom credentials and strict settings)"),
            (InstallProfile.CUSTOM.value, "Custom Configuration (Step-by-step custom options)"),
        ]
        chosen_profile = prompt_choice("Choose installation profile:", profile_choices, default_index=0)
        context.profile = InstallProfile(chosen_profile)

    apply_profile_defaults(context)

    pipeline = build_pipeline(skip_deps=args.skip_deps)

    for step in pipeline:
        success = step.run(context)
        if not success:
            console.error(f"Installation aborted at step: {step.name}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
