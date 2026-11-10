"""Database configuration and provisioning step."""

import os
import socket
import subprocess
import time
from typing import Dict

from installer.context import DatabaseMode, InstallerContext
from installer.steps.base import BaseStep
from installer.ui.console import console
from installer.ui.prompts import (
    prompt_choice,
    prompt_confirm,
    prompt_password,
    prompt_text,
)


class DatabaseStep(BaseStep):
    """Configures database connection parameters."""

    @property
    def name(self) -> str:
        return "Database Configuration"

    def run(self, context: InstallerContext) -> bool:
        console.print_section(self.name)

        if context.interactive and context.database.mode != DatabaseMode.SKIP:
            self._prompt_database_config(context)

        if context.database.mode == DatabaseMode.SKIP:
            console.info("Skipping database configuration.")

        return True

    def _read_existing_env(self, context: InstallerContext) -> Dict[str, str]:
        env_path = context.env_file_path
        if not env_path.exists():
            return {}
        result: Dict[str, str] = {}
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                result[key.strip()] = val.strip()
        return result

    def _prompt_database_config(self, context: InstallerContext) -> None:
        choices = [
            (DatabaseMode.DOCKER.value, "Local Docker PostgreSQL container (recommended)"),
            (DatabaseMode.LOCAL.value, "Native local PostgreSQL service (already installed on host)"),
            (DatabaseMode.REMOTE.value, "Remote PostgreSQL database (Supabase, Neon, AWS RDS, etc.)"),
            (DatabaseMode.SKIP.value, "Skip database setup for now"),
        ]

        mode_str = prompt_choice("Select database provisioning strategy:", choices, default_index=0)
        mode = DatabaseMode(mode_str)
        context.database.mode = mode

        if mode == DatabaseMode.SKIP:
            console.info("Skipping database configuration.")
            return

        existing_env = self._read_existing_env(context)
        existing_host = existing_env.get("DATABASE_CONNECTION_HOST", "localhost:5432")
        default_host, default_port = (
            existing_host.split(":", 1) if ":" in existing_host else (existing_host, "5432")
        )

        is_local = mode in (DatabaseMode.LOCAL, DatabaseMode.DOCKER)
        host_label = "Database host" if is_local else "Database host (e.g. db.xxx.supabase.co)"
        context.database.host = prompt_text(host_label, default=default_host)
        port_str = prompt_text("Database port", default=default_port)
        context.database.port = int(port_str) if port_str.isdigit() else 5432
        default_pg_user = existing_env.get("POSTGRES_USER", "postgres")
        context.database.user = prompt_text("PostgreSQL username", default=default_pg_user)
        default_pg_pass = existing_env.get("POSTGRES_PASSWORD", "postgres")
        context.database.password = prompt_password("PostgreSQL password", default=default_pg_pass)
        default_pg_db = existing_env.get("POSTGRES_DATABASE", "trading")
        context.database.name = prompt_text("Database name", default=default_pg_db)


class DatabaseProvisioningStep(BaseStep):
    """Provisions local database container if requested and verifies connectivity."""

    @property
    def name(self) -> str:
        return "Database Provisioning & Connectivity Check"

    def run(self, context: InstallerContext) -> bool:
        console.print_section(self.name)

        if context.database.mode == DatabaseMode.SKIP:
            console.info("Skipping database provisioning.")
            return True

        if context.database.mode == DatabaseMode.DOCKER:
            self._start_docker_postgres(context)

        if context.dry_run:
            console.info(f"[dry-run] Would test connection to {context.database.host_with_port}")
            return True

        return self._verify_connection(context)

    def _start_docker_postgres(self, context: InstallerContext) -> None:
        if context.dry_run:
            console.info("[dry-run] Would launch docker compose up -d postgres")
            return

        compose_env = {
            **os.environ,
            "POSTGRES_USER": context.database.user,
            "POSTGRES_PASSWORD": context.database.password,
            "POSTGRES_DATABASE": context.database.name,
        }

        console.info("Starting PostgreSQL container via docker compose...")
        try:
            result = subprocess.run(
                ["docker", "compose", "up", "-d", "postgres"],
                cwd=str(context.project_root),
                capture_output=True,
                text=True,
                env=compose_env,
                check=False,
            )
            if result.returncode == 0:
                console.success("PostgreSQL container started successfully.")
                self._wait_for_port(context.database.host, context.database.port, timeout_seconds=15)
            else:
                console.warning(f"Failed to start Docker container: {result.stderr.strip()}")
        except (subprocess.SubprocessError, OSError) as exc:
            console.warning(f"Could not invoke docker compose: {exc}")

    def _wait_for_port(self, host: str, port: int, timeout_seconds: int = 15) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            if self._can_connect_socket(host, port):
                return True
            time.sleep(1)
        return False

    def _verify_connection(self, context: InstallerContext) -> bool:
        host = context.database.host
        port = context.database.port

        console.info(f"Testing network connectivity to {host}:{port}...")
        if self._can_connect_socket(host, port):
            console.success(f"Connection to {host}:{port} succeeded.")
            return True

        console.warning(f"Unable to connect to database host at {host}:{port}.")
        if context.interactive:
            proceed = prompt_confirm("Continue installation anyway?", default=True)
            return proceed
        return False

    def _can_connect_socket(self, host: str, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1.5)
                return sock.connect_ex((host, port)) == 0
        except OSError:
            return False
