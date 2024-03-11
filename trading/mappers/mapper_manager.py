from typing import Type, Any

from api.interfaces.mapper import Mapper


class MapperManager:
    def __init__(self) -> None:
        self.mappers: dict[str, Type[Mapper]] = {}

    def register_mapper(self, mapper_cls: Type[Mapper]) -> None:
        if mapper_cls.provider.name in self.mappers:
            raise ValueError(f"Mapper ${mapper_cls.provider.name} already registered.")

        if mapper_cls.provider.name is None:
            raise ValueError(f"Mapper provider ${mapper_cls.provider.name} is None.")

        self.mappers[mapper_cls.provider.name] = mapper_cls

    def map(self, data: Any, type_str: str) -> Any:
        if type_str in self.mappers:
            return self.mappers[type_str].map(data)
        else:
            raise ValueError(f"Mapper for type '{type_str}' not registered.")
