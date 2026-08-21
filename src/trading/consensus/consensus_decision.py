from __future__ import annotations

from dataclasses import dataclass

from api.interfaces.trade_action import TradeAction


@dataclass(frozen=True)
class ConsensusDecision:
    trade_action: TradeAction
    ticker_symbol: str
    votes: dict[str, bool]
    weights: dict[str, float]
    factor: float

    @property
    def true_count(self) -> int:
        return sum(1 for vote in self.votes.values() if vote)

    @property
    def total(self) -> int:
        return len(self.votes)

    @property
    def vote_ratio(self) -> float:
        return self.true_count / self.total if self.total else 0.0

    @property
    def weighted_vote_ratio(self) -> float:
        total_weight = sum(self.weights.values())
        if not total_weight:
            return 0.0
        true_weight = sum(
            weight for name, weight in self.weights.items() if self.votes.get(name)
        )
        return true_weight / total_weight

    @property
    def quorum_threshold(self) -> float:
        return self.factor / (1.0 + self.factor)

    @property
    def quorum_margin(self) -> float:
        return self.true_count - self.factor * (self.total - self.true_count)

    @property
    def quorum(self) -> bool:
        return self.total > 0 and self.quorum_margin >= 0
