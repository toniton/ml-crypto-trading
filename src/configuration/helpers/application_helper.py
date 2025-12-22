import importlib
import logging
import pkgutil

from src.configuration.environment_config import AppEnvEnum


class ApplicationHelper:
    ASSETS_CONFIG_PATH = "src/configuration/assets.yaml"

    @staticmethod
    def get_application_config_path(app_env: AppEnvEnum) -> str:
        return f"src/configuration/application-{app_env.value}.yaml"

    @staticmethod
    def import_modules(package):
        for (_, name, _) in pkgutil.iter_modules(package.__path__):
            try:
                importlib.import_module(f".{name}", package.__name__)
            except ImportError as exc:
                logging.warning(f"Skipping {name}: {exc}")
