from __future__ import annotations

from pydantic_settings import BaseSettings, InitSettingsSource, YamlConfigSettingsSource


class CustomYamlConfigSettingsSource(YamlConfigSettingsSource):
    def __init__(
            self,
            init_settings: InitSettingsSource,
            settings_cls: type[BaseSettings],
    ) -> None:
        yaml_file = init_settings.init_kwargs.get("_yaml_file")
        super().__init__(settings_cls, yaml_file=yaml_file)
