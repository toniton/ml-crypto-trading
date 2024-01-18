from typing import Protocol, Any, TypeVar, Type

_T = TypeVar('_T')


class Mapper(Protocol):
    _instances = None

    @staticmethod
    def map(data: Any) -> Any:
        raise NotImplementedError()


class SingletonMapperMeta(type):
    _instances: dict[TypeVar, 'Mapper'] = {}

    def __call__(cls: Type['Mapper'], *args, **kwargs) -> 'Mapper':
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
