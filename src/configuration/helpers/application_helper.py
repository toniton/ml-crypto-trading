from src.configuration.environment_config import AppEnvEnum


class ApplicationHelper:
    ASSETS_CONFIG_PATH = "src/configuration/assets.yaml"

    @staticmethod
    def get_application_config_path(app_env: AppEnvEnum) -> str:
        return f"src/configuration/application-{app_env.value}.yaml"
