"""Preflight environment inspection step."""

import platform
import shutil
import socket
import subprocess
import sys

from installer.context import InstallerContext
from installer.steps.base import BaseStep
from installer.ui.console import console

MINIMUM_PYTHON_MAJOR = 3
MINIMUM_PYTHON_MINOR = 11


class PreflightStep(BaseStep):
    """Verifies system prerequisites before installation proceeds."""

    @property
    def name(self) -> str:
        return "System & Environment Preflight Check"

    def run(self, context: InstallerContext) -> bool:
        console.print_section(self.name)

        if not self._check_python_version():
            return False

        os_name = self._detect_os()
        console.info(f"Operating System: {os_name} ({platform.machine()})")

        if context.dry_run:
            console.info("[dry-run] Skipping Docker daemon and port probes during dry run.")
            return True

        docker_available = self._check_docker()
        if docker_available:
            console.success("Docker engine is running.")
        else:
            console.warning("Docker engine is not active or not installed.")

        port_busy = self._is_port_in_use("localhost", 5432)
        if port_busy:
            console.info("Port 5432 is currently occupied (an existing PostgreSQL instance may be running).")
        else:
            console.info("Port 5432 is free.")

        return True

    def _check_python_version(self) -> bool:
        major, minor = sys.version_info[:2]
        micro = sys.version_info[2] if len(sys.version_info) > 2 else 0
        current_version_str = f"{major}.{minor}.{micro}"

        if (major, minor) < (MINIMUM_PYTHON_MAJOR, MINIMUM_PYTHON_MINOR):
            console.error(
                f"Python {MINIMUM_PYTHON_MAJOR}.{MINIMUM_PYTHON_MINOR}+ is required. "
                f"Found: {current_version_str}"
            )
            return False

        console.success(f"Python version: {current_version_str}")
        return True

    def _detect_os(self) -> str:
        system = platform.system()
        if system == "Darwin":
            return f"macOS {platform.mac_ver()[0]}"
        if system == "Linux":
            return f"Linux ({platform.release()})"
        if system == "Windows":
            return f"Windows {platform.release()}"
        return system

    def _check_docker(self) -> bool:
        docker_bin = shutil.which("docker")
        if not docker_bin:
            return False
        try:
            result = subprocess.run(
                [docker_bin, "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def _is_port_in_use(self, host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.8)
            return sock.connect_ex((host, port)) == 0
