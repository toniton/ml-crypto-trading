from pydantic.v1.dataclasses import dataclass

from api.interfaces.mapper import Mapper


@dataclass(config={"arbitrary_types_allowed": True})
class MapperSocketMessage:
    action: str
    mapper: Mapper
