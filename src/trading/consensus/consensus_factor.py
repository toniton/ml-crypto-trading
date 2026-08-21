from pydantic import BaseModel


class ConsensusFactor(BaseModel):
    buy: float
    sell: float
