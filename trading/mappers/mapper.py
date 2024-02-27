from typing import Protocol, Any, TypeVar, Type

from entities.exchange_provider import ExchangeProvidersEnum

_T = TypeVar('_T')


class Mapper(Protocol):
    _instances = None

    provider: ExchangeProvidersEnum = None

    @staticmethod
    def map(data: Any) -> Any:
        raise NotImplementedError()


class SingletonMapperMeta(type):
    _instances: dict[TypeVar, 'Mapper'] = {}

    def __call__(cls: Type['Mapper'], *args, **kwargs) -> 'Mapper':
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
