from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

from api.interfaces.asset_schedule import AssetSchedule
from src.configuration.helpers.yaml_config_settings_source import CustomYamlConfigSettingsSource


class LlmProvider(str, Enum):
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"
    GROQ = "groq"


class LlmModelConfig(BaseModel):
    name: str = Field(description="Logical name used to select the model.")
    provider: LlmProvider = LlmProvider.OLLAMA
    model_name: str = Field(description="Provider-specific model identifier.")
    api_base_url: Optional[str] = Field(
        default=None,
        description="Provider endpoint override. If unset, the provider's default is used.",
    )
    temperature: float = 0.0
    timeout: Optional[float] = Field(default=None, description="Request timeout in seconds.")
    keep_alive: Optional[str] = Field(
        default=None,
        description="Keep-alive window for local Ollama models.",
    )
    capabilities: list[str] = Field(default_factory=list, description="tools, reasoning, vision.")
    roles: list[str] = Field(default_factory=list, description="Reserved; not supported yet.")
    api_key_env: Optional[str] = Field(
        default=None,
        description="Environment variable holding the API key. Falls back to the provider-specific env var.",
    )
    default: bool = Field(default=False, description="Selects this model when no name is given.")

    model_config = SettingsConfigDict(extra="ignore")


class LlmConfig(BaseSettings):
    """Infrastructure configuration for the AI subsystem.

    Describes available models and providers; it carries no trading behavior.
    """

    schedule: AssetSchedule = AssetSchedule.EVERY_HOUR
    models: list[LlmModelConfig] = Field(default_factory=list)

    _yaml_file: str = "src/configuration/llm.yaml"
    model_config = SettingsConfigDict(
        yaml_file=_yaml_file,
        yaml_file_encoding="utf-8",
        env_file=".env",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls,
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
    ):
        return (
            env_settings, dotenv_settings, YamlConfigSettingsSource(settings_cls),
            CustomYamlConfigSettingsSource(init_settings, settings_cls)
        )

    @property
    def default_model(self) -> LlmModelConfig:
        for model in self.models:
            if model.default:
                return model
        return self.models[0]

    def get_model(self, name: str) -> LlmModelConfig:
        for model in self.models:
            if model.name == name:
                return model
        raise ValueError(f"Model '{name}' not registered in the LLM configuration.")