"""Database configuration and provisioning step."""

import socket
import subprocess
import time
from typing import Optional

from installer.context import DatabaseConfig, DatabaseMode, InstallerContext
from installer.steps.base import BaseStep
from installer.ui.console import console
from installer.ui.prompts import (
    prompt_choice,
    prompt_confirm,
    prompt_password,
    prompt_text,
)


class DatabaseStep(BaseStep):
    """Configures database connection and provisions local container if requested."""

    @property
    def name(self) -> str:
        return "Database Setup & Provisioning"

    def run(self, context: InstallerContext) -> bool:
        console.print_section(self.name)

        if context.interactive:
            self._prompt_database_config(context)

        if context.database.mode == DatabaseMode.DOCKER:
            self._start_docker_postgres(context)

        if context.database.mode != DatabaseMode.SKIP:
            self._verify_connection(context)

        return True

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

        if mode in (DatabaseMode.LOCAL, DatabaseMode.DOCKER):
            host = prompt_text("Database host", default="localhost")
            port_str = prompt_text("Database port", default="5432")
            user = prompt_text("PostgreSQL username", default="postgres")
            password = prompt_password("PostgreSQL password", default="postgres")
            dbname = prompt_text("Database name", default="trading")
        else:
            host_input = prompt_text("Database host (e.g. db.xxx.supabase.co)", default="localhost")
            port_str = prompt_text("Database port", default="5432")
            user = prompt_text("PostgreSQL username", default="postgres")
            password = prompt_password("PostgreSQL password")
            dbname = prompt_text("Database name", default="trading")
            host = host_input

        context.database.host = host
        context.database.port = int(port_str) if port_str.isdigit() else 5432
        context.database.user = user
        context.database.password = password
        context.database.name = dbname

    def _start_docker_postgres(self, context: InstallerContext) -> None:
        if context.dry_run:
            console.info("[dry-run] Would launch docker compose up -d postgres")
            return

        console.info("Starting PostgreSQL container via docker compose...")
        try:
            result = subprocess.run(
                ["docker", "compose", "up", "-d", "postgres"],
                cwd=str(context.project_root),
                capture_output=True,
                text=True,
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
