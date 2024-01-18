import abc
from typing import Any


class PreProcessor(abc.ABC):
    @abc.abstractmethod
    def pre_process_data(self, data: Any):
        raise NotImplementedError()