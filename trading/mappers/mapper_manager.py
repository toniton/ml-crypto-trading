from typing import Type, Any

from trading.mappers.mapper import Mapper


class MapperManager:
    def __init__(self) -> None:
        self.mappers: dict[str, Type[Mapper]] = {}

    def register_mapper(self, type_str: str, mapper_cls: Type[Mapper]) -> None:
        if type_str in self.mappers:
            raise ValueError(f"Mapper ${type_str} already registered.")
        self.mappers[type_str] = mapper_cls

    def map(self, data: Any, type_str: str) -> Any:
        if type_str in self.mappers:
            return self.mappers[type_str].map(data)
        else:
            raise ValueError(f"Mapper for type '{type_str}' not registered.")
