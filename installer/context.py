"""Installation state context and data models."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class InstallProfile(str, Enum):
    """Available installation profiles."""
    QUICKSTART = "quickstart"
    DEVELOPER = "developer"
    PRODUCTION = "production"
    CUSTOM = "custom"


class DatabaseMode(str, Enum):
    """Supported database deployment modes."""
    DOCKER = "docker"
    LOCAL = "local"
    REMOTE = "remote"
    SKIP = "skip"


@dataclass
class DatabaseConfig:
    """Database connection and provisioning settings."""
    mode: DatabaseMode = DatabaseMode.DOCKER
    host: str = "localhost"
    port: int = 5432
    name: str = "trading"
    user: str = "postgres"
    password: str = "postgres"

    @property
    def host_with_port(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass
class CredentialsConfig:
    """API credentials for external services."""
    crypto_dot_com_key: str = ""
    crypto_dot_com_secret: str = ""
    binance_key: str = ""
    binance_secret: str = ""
    deepseek_key: str = ""
    gemini_key: str = ""
    groq_key: str = ""


@dataclass
class AppConfig:
    """Application runtime configuration."""
    app_env: str = "production"
    log_level: str = "INFO"


@dataclass
class InstallerContext:
    """Carries full state across all installer steps."""
    project_root: Path
    venv_dir: Path
    profile: InstallProfile = InstallProfile.QUICKSTART
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    credentials: CredentialsConfig = field(default_factory=CredentialsConfig)
    app: AppConfig = field(default_factory=AppConfig)
    install_dev_deps: bool = False
    run_migrations: bool = True
    start_service: bool = False
    dry_run: bool = False
    interactive: bool = True

    @property
    def env_file_path(self) -> Path:
        return self.project_root / ".env"

    @property
    def env_example_path(self) -> Path:
        return self.project_root / ".env.example"
