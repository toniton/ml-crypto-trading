from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple, Any, Dict
import yaml
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings
from pydantic_settings.sources import DotenvType, PydanticBaseSettingsSource


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    def __init__(
            self,
            settings_cls: type[BaseSettings],
            yaml_file: DotenvType | None = None,
            yaml_file_encoding: str | None = None,
    ) -> None:
        self.yaml_file = (yaml_file if yaml_file is not None else settings_cls.model_config.get('env_file'))
        self.yaml_file_encoding = (
            yaml_file_encoding if yaml_file_encoding is not None else settings_cls.model_config.get('env_file_encoding')
        )
        super().__init__(settings_cls)

    def get_field_value(
            self, field: FieldInfo, field_name: str
    ) -> Tuple[Any, str, bool]:
        if field.exclude:
            return None, "", False
        file = self.yaml_file
        encoding = self.yaml_file_encoding
        path = Path(os.path.dirname(__file__), os.pardir, file)
        with open(path, 'r', encoding=encoding) as config_file:
            try:
                configuration = yaml.safe_load(config_file)
                return configuration[field_name], field_name, False
            except Exception as exc:
                raise ValueError(f"Unsupported yaml file format! {path}, {exc}") from exc

    def __call__(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}

        for field_name, field in self.settings_cls.model_fields.items():
            field_value, field_key, value_is_complex = self.get_field_value(
                field, field_name
            )
            if field_value is not None:
                d[field_key] = field_value

        return d
