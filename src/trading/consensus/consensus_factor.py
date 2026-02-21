from pydantic import BaseModel


class ConsensusFactor(BaseModel):
    buy: float = 1.3
    sell: float = 0.5
