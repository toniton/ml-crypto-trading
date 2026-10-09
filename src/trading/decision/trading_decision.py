from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from api.interfaces.trade_action import TradeAction


class DecisionStatus(str, Enum):
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class MarketSnapshot:
    close_price: Decimal
    bid_price: Optional[Decimal] = None
    ask_price: Optional[Decimal] = None
    spread_pct: Optional[Decimal] = None
    candles_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "close_price": str(self.close_price),
            "bid_price": str(self.bid_price) if self.bid_price is not None else None,
            "ask_price": str(self.ask_price) if self.ask_price is not None else None,
            "spread_pct": str(self.spread_pct) if self.spread_pct is not None else None,
            "candles_count": self.candles_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketSnapshot:
        return cls(
            close_price=Decimal(str(data.get("close_price", 0))),
            bid_price=Decimal(str(data["bid_price"])) if data.get("bid_price") is not None else None,
            ask_price=Decimal(str(data["ask_price"])) if data.get("ask_price") is not None else None,
            spread_pct=Decimal(str(data["spread_pct"])) if data.get("spread_pct") is not None else None,
            candles_count=int(data.get("candles_count", 0)),
        )


@dataclass(frozen=True)
class RegimeSnapshot:
    regime: str
    volatility: float
    trend_strength: float
    spread: float
    exposure_multiplier: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegimeSnapshot:
        return cls(
            regime=str(data.get("regime", "NORMAL")),
            volatility=float(data.get("volatility", 0.0)),
            trend_strength=float(data.get("trend_strength", 0.0)),
            spread=float(data.get("spread", 0.0)),
            exposure_multiplier=float(data.get("exposure_multiplier", 1.0)),
        )


@dataclass(frozen=True)
class ConsensusSnapshot:
    action: TradeAction
    votes: dict[str, bool]
    weights: dict[str, float]
    factor: float
    quorum: bool
    quorum_margin: float
    vote_ratio: float
    winning_strategy: Optional[str] = None
    strategy_attributions: Optional[dict[str, float]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value if isinstance(self.action, TradeAction) else str(self.action),
            "votes": self.votes,
            "weights": self.weights,
            "factor": self.factor,
            "quorum": self.quorum,
            "quorum_margin": self.quorum_margin,
            "vote_ratio": self.vote_ratio,
            "winning_strategy": self.winning_strategy,
            "strategy_attributions": self.strategy_attributions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConsensusSnapshot:
        return cls(
            action=TradeAction(data["action"]) if isinstance(data.get("action"), str) else data.get("action", TradeAction.BUY),
            votes={k: bool(v) for k, v in data.get("votes", {}).items()},
            weights={k: float(v) for k, v in data.get("weights", {}).items()},
            factor=float(data.get("factor", 1.0)),
            quorum=bool(data.get("quorum", False)),
            quorum_margin=float(data.get("quorum_margin", 0.0)),
            vote_ratio=float(data.get("vote_ratio", 0.0)),
            winning_strategy=data.get("winning_strategy"),
            strategy_attributions=data.get("strategy_attributions"),
        )


@dataclass(frozen=True)
class SizingSnapshot:
    formula: Optional[str] = None
    calculated_quantity: Optional[Decimal] = None
    min_quantity: Decimal = Decimal("0")
    final_quantity: Optional[Decimal] = None
    variables: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "formula": self.formula,
            "calculated_quantity": str(self.calculated_quantity) if self.calculated_quantity is not None else None,
            "min_quantity": str(self.min_quantity),
            "final_quantity": str(self.final_quantity) if self.final_quantity is not None else None,
            "variables": {
                k: str(v) if isinstance(v, Decimal) else v
                for k, v in self.variables.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SizingSnapshot:
        return cls(
            formula=data.get("formula"),
            calculated_quantity=Decimal(str(data["calculated_quantity"])) if data.get("calculated_quantity") is not None else None,
            min_quantity=Decimal(str(data.get("min_quantity", 0))),
            final_quantity=Decimal(str(data["final_quantity"])) if data.get("final_quantity") is not None else None,
            variables=data.get("variables", {}),
        )


@dataclass(frozen=True)
class PortfolioSnapshot:
    available_cash: Decimal = Decimal("0")
    total_equity: Decimal = Decimal("0")
    current_exposure_pct: float = 0.0
    asset_exposure_pct: float = 0.0
    drawdown_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "available_cash": str(self.available_cash),
            "total_equity": str(self.total_equity),
            "current_exposure_pct": self.current_exposure_pct,
            "asset_exposure_pct": self.asset_exposure_pct,
            "drawdown_pct": self.drawdown_pct,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PortfolioSnapshot:
        return cls(
            available_cash=Decimal(str(data.get("available_cash", 0))),
            total_equity=Decimal(str(data.get("total_equity", 0))),
            current_exposure_pct=float(data.get("current_exposure_pct", 0.0)),
            asset_exposure_pct=float(data.get("asset_exposure_pct", 0.0)),
            drawdown_pct=float(data.get("drawdown_pct", 0.0)),
        )


@dataclass(frozen=True)
class RiskEvaluation:
    passed: bool
    effective_max_per_asset: Optional[Decimal] = None
    effective_max_total: Optional[Decimal] = None
    min_quote_reserve: Optional[Decimal] = None
    rejection_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "effective_max_per_asset": str(self.effective_max_per_asset) if self.effective_max_per_asset is not None else None,
            "effective_max_total": str(self.effective_max_total) if self.effective_max_total is not None else None,
            "min_quote_reserve": str(self.min_quote_reserve) if self.min_quote_reserve is not None else None,
            "rejection_reason": self.rejection_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskEvaluation:
        return cls(
            passed=bool(data.get("passed", False)),
            effective_max_per_asset=Decimal(str(data["effective_max_per_asset"])) if data.get("effective_max_per_asset") is not None else None,
            effective_max_total=Decimal(str(data["effective_max_total"])) if data.get("effective_max_total") is not None else None,
            min_quote_reserve=Decimal(str(data["min_quote_reserve"])) if data.get("min_quote_reserve") is not None else None,
            rejection_reason=data.get("rejection_reason"),
        )


@dataclass(frozen=True)
class HealthEvaluation:
    state: str
    allowed: bool
    active_conditions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "allowed": self.allowed,
            "active_conditions": self.active_conditions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HealthEvaluation:
        return cls(
            state=str(data.get("state", "UNKNOWN")),
            allowed=bool(data.get("allowed", False)),
            active_conditions=list(data.get("active_conditions", [])),
        )


# pylint: disable=too-many-instance-attributes
@dataclass
class TradingDecision:
    ticker_symbol: str
    exchange: str
    trade_action: TradeAction
    market_snapshot: MarketSnapshot
    regime_snapshot: RegimeSnapshot
    consensus_snapshot: ConsensusSnapshot
    sizing_snapshot: SizingSnapshot
    portfolio_snapshot: PortfolioSnapshot
    risk_evaluation: RiskEvaluation
    decision_id: str = field(default_factory=lambda: f"dec_{uuid4().hex}")
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    status: DecisionStatus = DecisionStatus.EXECUTED
    rejection_reason: Optional[str] = None
    commit_hash: Optional[str] = None
    winning_strategy: Optional[str] = None
    strategy_attributions: Optional[dict[str, float]] = None
    resulting_order_id: Optional[str] = None
    health_evaluation: Optional[HealthEvaluation] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp,
            "ticker_symbol": self.ticker_symbol,
            "exchange": self.exchange,
            "trade_action": self.trade_action.value,
            "status": self.status.value,
            "rejection_reason": self.rejection_reason,
            "commit_hash": self.commit_hash,
            "winning_strategy": self.winning_strategy,
            "strategy_attributions": self.strategy_attributions,
            "resulting_order_id": self.resulting_order_id,
            "market_snapshot": self.market_snapshot.to_dict(),
            "regime_snapshot": self.regime_snapshot.to_dict(),
            "consensus_snapshot": self.consensus_snapshot.to_dict(),
            "sizing_snapshot": self.sizing_snapshot.to_dict(),
            "portfolio_snapshot": self.portfolio_snapshot.to_dict(),
            "risk_evaluation": self.risk_evaluation.to_dict(),
            "health_evaluation": self.health_evaluation.to_dict() if self.health_evaluation else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TradingDecision:
        return cls(
            decision_id=data.get("decision_id", f"dec_{uuid4().hex}"),
            timestamp=float(data.get("timestamp", datetime.now(timezone.utc).timestamp())),
            ticker_symbol=data["ticker_symbol"],
            exchange=data["exchange"],
            trade_action=TradeAction(data["trade_action"]) if isinstance(data["trade_action"], str) else data["trade_action"],
            status=DecisionStatus(data["status"]) if isinstance(data.get("status"), str) else data.get("status", DecisionStatus.EXECUTED),
            rejection_reason=data.get("rejection_reason"),
            commit_hash=data.get("commit_hash"),
            winning_strategy=data.get("winning_strategy"),
            strategy_attributions=data.get("strategy_attributions"),
            resulting_order_id=data.get("resulting_order_id"),
            market_snapshot=MarketSnapshot.from_dict(data["market_snapshot"]),
            regime_snapshot=RegimeSnapshot.from_dict(data["regime_snapshot"]),
            consensus_snapshot=ConsensusSnapshot.from_dict(data["consensus_snapshot"]),
            sizing_snapshot=SizingSnapshot.from_dict(data["sizing_snapshot"]),
            portfolio_snapshot=PortfolioSnapshot.from_dict(data["portfolio_snapshot"]),
            risk_evaluation=RiskEvaluation.from_dict(data["risk_evaluation"]),
            health_evaluation=(
                HealthEvaluation.from_dict(data["health_evaluation"])
                if data.get("health_evaluation")
                else None
            ),
            metadata=data.get("metadata", {}),
        )
