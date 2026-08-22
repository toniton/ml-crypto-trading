from pydantic import BaseModel, Field


class ConsensusFactor(BaseModel):
    buy: float = Field(
        ge=0.05,
        le=10.0,
        description="Consensus threshold that must be reached for a BUY signal.",
        json_schema_extra={"mutable": True},
    )
    sell: float = Field(
        ge=0.05,
        le=10.0,
        description="Consensus threshold that must be reached for a SELL signal.",
        json_schema_extra={"mutable": True},
    )
