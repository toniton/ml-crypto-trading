from __future__ import annotations

from datetime import datetime, timezone

from api.interfaces.trade_action import TradeAction
from src.database.dao.trading_decision_dao import TradingDecisionDao
from src.trading.decision.trading_decision import (
    ConsensusSnapshot,
    DecisionStatus,
    HealthEvaluation,
    MarketSnapshot,
    PortfolioSnapshot,
    RegimeSnapshot,
    RiskEvaluation,
    SizingSnapshot,
    TradingDecision,
)


class TradingDecisionDbVsEntityMapper:
    @staticmethod
    def map_to_db(entity: TradingDecision) -> TradingDecisionDao:
        ts = (
            datetime.fromtimestamp(entity.timestamp, tz=timezone.utc)
            if isinstance(entity.timestamp, (int, float))
            else datetime.now(timezone.utc)
        )
        return TradingDecisionDao(
            id=entity.decision_id,
            timestamp=ts,
            ticker_symbol=entity.ticker_symbol,
            exchange=entity.exchange,
            trade_action=entity.trade_action.value if isinstance(entity.trade_action, TradeAction) else str(entity.trade_action),
            status=entity.status.value if isinstance(entity.status, DecisionStatus) else str(entity.status),
            rejection_reason=entity.rejection_reason,
            commit_hash=entity.commit_hash,
            winning_strategy=entity.winning_strategy,
            resulting_order_id=entity.resulting_order_id,
            market_snapshot=entity.market_snapshot.to_dict(),
            regime_snapshot=entity.regime_snapshot.to_dict(),
            consensus_snapshot=entity.consensus_snapshot.to_dict(),
            sizing_snapshot=entity.sizing_snapshot.to_dict(),
            portfolio_snapshot=entity.portfolio_snapshot.to_dict(),
            risk_evaluation=entity.risk_evaluation.to_dict(),
            health_evaluation=entity.health_evaluation.to_dict() if entity.health_evaluation else None,
            metadata_=entity.metadata or {},
        )

    @staticmethod
    def map_to_entity(dao: TradingDecisionDao) -> TradingDecision:
        if dao.timestamp.tzinfo is None:
            ts = dao.timestamp.replace(tzinfo=timezone.utc).timestamp()
        else:
            ts = dao.timestamp.astimezone(timezone.utc).timestamp()

        trade_action = (
            TradeAction(dao.trade_action)
            if dao.trade_action in TradeAction._value2member_map_
            else TradeAction.BUY
        )
        status = (
            DecisionStatus(dao.status)
            if dao.status in DecisionStatus._value2member_map_
            else DecisionStatus.EXECUTED
        )

        return TradingDecision(
            decision_id=dao.id,
            timestamp=ts,
            ticker_symbol=dao.ticker_symbol,
            exchange=dao.exchange,
            trade_action=trade_action,
            status=status,
            rejection_reason=dao.rejection_reason,
            commit_hash=dao.commit_hash,
            winning_strategy=dao.winning_strategy,
            resulting_order_id=dao.resulting_order_id,
            market_snapshot=MarketSnapshot.from_dict(dao.market_snapshot or {}),
            regime_snapshot=RegimeSnapshot.from_dict(dao.regime_snapshot or {}),
            consensus_snapshot=ConsensusSnapshot.from_dict(dao.consensus_snapshot or {}),
            sizing_snapshot=SizingSnapshot.from_dict(dao.sizing_snapshot or {}),
            portfolio_snapshot=PortfolioSnapshot.from_dict(dao.portfolio_snapshot or {}),
            risk_evaluation=RiskEvaluation.from_dict(dao.risk_evaluation or {}),
            health_evaluation=(
                HealthEvaluation.from_dict(dao.health_evaluation)
                if dao.health_evaluation
                else None
            ),
            metadata=dao.metadata_ or {},
        )
