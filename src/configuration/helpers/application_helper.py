from src.configuration.environment_config import AppEnvEnum


class ApplicationHelper:
    @staticmethod
    def get_env_path(app_env: AppEnvEnum) -> str:
        return f"src/configuration/application-{app_env.value}.yaml"
