"""Environment file (.env) generation and synchronization step."""

from datetime import datetime
from pathlib import Path
import re
import shutil
from typing import Dict

from installer.context import DatabaseMode, InstallerContext
from installer.steps.base import BaseStep
from installer.ui.console import console


class EnvironmentStep(BaseStep):
    """Writes environment configuration to .env safely with backup."""

    @property
    def name(self) -> str:
        return "Environment File (.env) Configuration"

    def run(self, context: InstallerContext) -> bool:
        console.print_section(self.name)

        env_path = context.env_file_path
        example_path = context.env_example_path

        if context.dry_run:
            console.info(f"[dry-run] Would generate and write configuration to {env_path}")
            return True

        if env_path.exists():
            backup_path = self._create_backup(env_path)
            console.info(f"Backed up existing .env to {backup_path.name}")
        elif example_path.exists():
            shutil.copy(example_path, env_path)
            console.info(f"Initialized .env from {example_path.name}")
        else:
            env_path.touch()
            console.info("Created new empty .env file")

        variables = self._build_variable_map(context)
        self._apply_variables(env_path, variables)
        console.success(f"Updated {env_path.name} with configuration settings.")
        return True

    def _create_backup(self, env_path: Path) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = env_path.parent / f".env.backup.{timestamp}"
        shutil.copy(env_path, backup_path)
        return backup_path

    def _build_variable_map(self, context: InstallerContext) -> Dict[str, str]:
        var_map: Dict[str, str] = {
            "APP_ENV": context.app.app_env,
            "LOG_LEVEL": context.app.log_level,
        }

        if context.database.mode != DatabaseMode.SKIP:
            var_map["DATABASE_CONNECTION_HOST"] = context.database.host_with_port
            var_map["POSTGRES_USER"] = context.database.user
            var_map["POSTGRES_PASSWORD"] = context.database.password
            var_map["POSTGRES_DATABASE"] = context.database.name

        creds = context.credentials
        if creds.crypto_dot_com_key:
            var_map["CRYPTO_DOT_COM__API_KEY"] = creds.crypto_dot_com_key
        if creds.crypto_dot_com_secret:
            var_map["CRYPTO_DOT_COM__SECRET_KEY"] = creds.crypto_dot_com_secret
        if creds.binance_key:
            var_map["CCXT_PROVIDERS__BINANCE__API_KEY"] = creds.binance_key
        if creds.binance_secret:
            var_map["CCXT_PROVIDERS__BINANCE__SECRET_KEY"] = creds.binance_secret
        if creds.deepseek_key:
            var_map["LLM_PROVIDER__DEEPSEEK__API_KEY"] = creds.deepseek_key
        if creds.gemini_key:
            var_map["LLM_PROVIDER__GEMINI__API_KEY"] = creds.gemini_key
        if creds.groq_key:
            var_map["LLM_PROVIDER__GROQ__API_KEY"] = creds.groq_key

        return var_map

    def _apply_variables(self, env_path: Path, variables: Dict[str, str]) -> None:
        content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

        for key, val in variables.items():
            pattern = rf"^{re.escape(key)}=.*$"
            replacement = f"{key}={val}"
            if re.search(pattern, content, flags=re.MULTILINE):
                content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            else:
                content = content.rstrip() + f"\n{replacement}\n"

        env_path.write_text(content, encoding="utf-8")
