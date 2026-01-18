from typing import Any

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass


@dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class MapperSocketMessage:
    action: str
    mapper: Any
