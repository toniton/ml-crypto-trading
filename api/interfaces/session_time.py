import time
from pydantic.dataclasses import dataclass


@dataclass
class SessionTime:
    start_time: float = time.time()
    end_time: float = time.time()

    @property
    def duration(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time
