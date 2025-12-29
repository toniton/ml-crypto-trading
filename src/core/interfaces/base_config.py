import abc

from src.configuration.environment_config import EnvironmentConfig


class BaseConfig(abc.ABC, metaclass=abc.ABCMeta):
    _instance = None

    @abc.abstractmethod
    def __init__(self, env_config: EnvironmentConfig = None):
        self.env_config = env_config

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = cls(*args, **kwargs)
        return cls._instance
