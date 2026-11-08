from __future__ import annotations

import collections
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Deque, Dict, List, Optional

from pydantic import BaseModel

from api.interfaces.backtest_request import ExecutionConfiguration
from api.interfaces.order import Order
from api.interfaces.trade import Trade
from api.interfaces.trade_action import TradeAction
from src.backtest.analysis.calculators.execution_quality_calculator import ExecutionQualityCalculator
from src.backtest.analysis.calculators.portfolio_risk_calculator import PortfolioRiskCalculator
from src.backtest.analysis.calculators.risk_adjusted_calculator import RiskAdjustedCalculator
from src.backtest.analysis.calculators.trading_behavior_calculator import TradingBehaviorCalculator
from src.backtest.domain.metrics import (
    ExecutionQualityMetrics,
    PortfolioRiskMetrics,
    RiskAdjustedMetrics,
    TradingBehaviorMetrics,
)
from src.backtest.domain.result import BacktestFill, BacktestResult, PortfolioSnapshot
from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.trading_engine_proxy import AssetRuntimeSnapshot, TradingEngineProxy
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.database.repositories.providers.postgres_trading_decision_repository import (
    PostgresTradingDecisionRepository,
)
from src.trading.analytics.trade_attribution_service import (
    AttributionMetrics,
    TradeAttributionService,
)


class PeriodModel(BaseModel):
    start: str
    end: str


class PerformanceSummary(BaseModel):
    trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    volume: str
    fees: str
    realized_pnl: str
    average_trade_pnl: str
    profit_factor: float
    buy_count: int
    sell_count: int


class DailyPerformance(BaseModel):
    date: str
    trades: int
    volume: str
    fees: str
    realized_pnl: str


class TradeExecutionItem(BaseModel):
    order_id: str
    timestamp: str
    side: str
    price: str
    fill_price: str
    quantity: str
    fees: str
    realized_pnl: Optional[str] = None


class AssetEquityPointModel(BaseModel):
    timestamp: str
    equity: str
    cumulative_pnl: str
    drawdown_pct: float


class StrategyAttributionModel(BaseModel):
    total_trades: int
    winning_trades: int
    losing_trades: int
    break_even_trades: int
    win_rate_pct: float
    gross_pnl: str
    total_fees: str
    total_slippage: str
    net_pnl: str
    profit_factor: float
    avg_return_pct: float
    avg_duration_seconds: float
    max_win: str
    max_loss: str

    @classmethod
    def from_attribution_metrics(cls, metrics: AttributionMetrics) -> StrategyAttributionModel:
        return cls(
            total_trades=metrics.total_trades,
            winning_trades=metrics.winning_trades,
            losing_trades=metrics.losing_trades,
            break_even_trades=metrics.break_even_trades,
            win_rate_pct=metrics.win_rate_pct,
            gross_pnl=f"{metrics.gross_pnl:+.2f}",
            total_fees=f"{metrics.total_fees:.4f}",
            total_slippage=f"{metrics.total_slippage:.4f}",
            net_pnl=f"{metrics.net_pnl:+.2f}",
            profit_factor=metrics.profit_factor,
            avg_return_pct=metrics.avg_return_pct,
            avg_duration_seconds=metrics.avg_duration_seconds,
            max_win=f"{metrics.max_win:+.2f}",
            max_loss=f"{metrics.max_loss:+.2f}",
        )


class AssetPerformanceResponse(BaseModel):
    ticker_symbol: str
    period: PeriodModel
    summary: PerformanceSummary
    daily: List[DailyPerformance]
    trades: List[TradeExecutionItem]
    equity_curve: List[AssetEquityPointModel] = []
    starting_balance: Optional[str] = None
    current_equity: Optional[str] = None
    strategy_attribution: Dict[str, StrategyAttributionModel] = {}
    commit_attribution: Dict[str, StrategyAttributionModel] = {}
    risk_adjusted: Optional[RiskAdjustedMetrics] = None
    behavior: Optional[TradingBehaviorMetrics] = None
    execution: Optional[ExecutionQualityMetrics] = None
    portfolio: Optional[PortfolioRiskMetrics] = None


class BuyLot:
    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            order_uuid: str,
            remaining_qty: Decimal,
            buy_price: Decimal,
            fee_per_unit: Decimal,
            entry_timestamp: float,
            slippage_per_unit: Decimal = Decimal("0"),
            commit_hash: Optional[str] = None,
            winning_strategy: Optional[str] = None,
            strategy_votes: Optional[dict[str, str]] = None,
            strategy_attributions: Optional[dict[str, float]] = None,
            regime: Optional[str] = None,
    ) -> None:
        self.order_uuid = order_uuid
        self.remaining_qty = remaining_qty
        self.buy_price = buy_price
        self.fee_per_unit = fee_per_unit
        self.entry_timestamp = entry_timestamp
        self.slippage_per_unit = slippage_per_unit
        self.commit_hash = commit_hash
        self.winning_strategy = winning_strategy
        self.strategy_votes = strategy_votes
        self.strategy_attributions = strategy_attributions
        self.regime = regime


@dataclass(frozen=True)
class TradeExtractionResult:
    trades: List[Trade]
    unmatched_exit_quantity: Decimal
    unmatched_exit_orders: int


@dataclass(frozen=True)
class FillEquityStep:
    timestamp: float
    cumulative_pnl: Decimal


class AssetPerformanceService:
    def __init__(
            self,
            database_manager: DatabaseManager,
            trading_proxy: Optional[TradingEngineProxy] = None,
    ) -> None:
        self._database_manager = database_manager
        self._trading_proxy = trading_proxy

    def calculate_performance(
            self,
            ticker_symbol: str,
            start: datetime,
            end: datetime,
    ) -> AssetPerformanceResponse:
        orders = self._fetch_completed_orders(ticker_symbol, start, end)
        runtime_snapshot = self._fetch_runtime_snapshot(ticker_symbol)
        return self.compute_metrics(
            ticker_symbol,
            start,
            end,
            orders,
            runtime_snapshot=runtime_snapshot,
        )

    def _fetch_runtime_snapshot(self, ticker_symbol: str) -> Optional[AssetRuntimeSnapshot]:
        snapshot: Optional[AssetRuntimeSnapshot] = None
        if self._trading_proxy is not None:
            try:
                snapshot = self._trading_proxy.get_asset_snapshot(ticker_symbol)
            except Exception:  # pylint: disable=broad-except
                snapshot = None

        if snapshot is not None and (
            snapshot.available_balance is not None or snapshot.starting_balance is not None
        ):
            return snapshot

        db_snapshot = self._fetch_decision_snapshot(ticker_symbol)
        if db_snapshot is not None:
            return db_snapshot

        peer_snapshot = self._fetch_peer_quote_snapshot(ticker_symbol)
        return peer_snapshot if peer_snapshot is not None else snapshot

    def _fetch_peer_quote_snapshot(self, ticker_symbol: str) -> Optional[AssetRuntimeSnapshot]:
        if self._trading_proxy is None or "_" not in ticker_symbol:
            return None
        quote_suffix = f"_{ticker_symbol.split('_')[-1]}"
        try:
            status = self._trading_proxy.get_status()
            for monitored in getattr(status, "monitored_assets", []) or []:
                if monitored.endswith(quote_suffix):
                    peer = self._trading_proxy.get_asset_snapshot(monitored)
                    if peer is not None and peer.available_balance is not None:
                        return AssetRuntimeSnapshot(
                            ticker_symbol=ticker_symbol,
                            position_quantity=0.0,
                            available_balance=peer.available_balance,
                        )
        except Exception:  # pylint: disable=broad-except
            return None
        return None

    def _fetch_decision_snapshot(self, ticker_symbol: str) -> Optional[AssetRuntimeSnapshot]:
        try:
            with self._database_manager.get_unit_of_work() as uow:
                repo = uow.get_repository(PostgresTradingDecisionRepository)
                decisions = repo.get_by_ticker_symbol(ticker_symbol, limit=1)
                if not decisions:
                    return None
                latest = decisions[0]
                total_eq = getattr(latest.portfolio_snapshot, "total_equity", Decimal("0"))
                if not isinstance(total_eq, (int, float, Decimal)) or Decimal(str(total_eq)) <= Decimal("0"):
                    return None
                close_p = getattr(latest.market_snapshot, "close_price", None)
                latest_price = (
                    float(close_p)
                    if isinstance(close_p, (int, float, Decimal)) and float(close_p) > 0
                    else None
                )
                return AssetRuntimeSnapshot(
                    ticker_symbol=ticker_symbol,
                    position_quantity=0.0,
                    latest_price=latest_price,
                    starting_balance=float(total_eq),
                    available_balance=float(total_eq),
                )
        except Exception:  # pylint: disable=broad-except
            return None

    def _fetch_completed_orders(
        self, ticker_symbol: str, start: datetime, end: datetime
    ) -> List[Order]:
        with self._database_manager.get_unit_of_work() as uow:
            repository = uow.get_repository(PostgresOrderRepository)
            return repository.get_completed_by_ticker_and_executed_range(
                ticker_symbol=ticker_symbol,
                start=start,
                end=end,
            )

    @classmethod
    def extract_trades_with_audit(  # pylint: disable=too-many-locals
            cls, ticker_symbol: str, orders: List[Order]
    ) -> TradeExtractionResult:
        def get_exec_dt(o: Order) -> datetime:
            if o.executed_time is not None:
                return datetime.fromtimestamp(o.executed_time, tz=timezone.utc)
            return datetime.fromtimestamp(o.created_time, tz=timezone.utc)

        sorted_orders = sorted(orders, key=get_exec_dt)
        buy_lots: Deque[BuyLot] = collections.deque()
        matched_trades: List[Trade] = []
        unmatched_exit_quantity = Decimal("0")
        unmatched_exit_orders = 0

        for order in sorted_orders:
            action_raw = order.trade_action.value
            side = "BUY" if "BUY" in action_raw.upper() else "SELL"
            qty = Decimal(str(order.quantity or "0"))
            fill_price_val = Decimal(str(order.fill_price or order.price or "0"))
            fee_val = Decimal(str(order.fees or "0"))
            slippage_val = Decimal(str(order.slippage or "0"))
            exec_dt = get_exec_dt(order)

            if side == "BUY":
                fee_per_unit = (fee_val / qty) if qty > 0 else Decimal("0")
                slippage_per_unit = (slippage_val / qty) if qty > 0 else Decimal("0")
                buy_lots.append(
                    BuyLot(
                        order_uuid=order.uuid,
                        remaining_qty=qty,
                        buy_price=fill_price_val,
                        fee_per_unit=fee_per_unit,
                        entry_timestamp=exec_dt.timestamp(),
                        slippage_per_unit=slippage_per_unit,
                        commit_hash=order.commit_hash,
                        winning_strategy=order.winning_strategy,
                        strategy_votes=order.strategy_votes,
                        strategy_attributions=order.strategy_attributions,
                        regime=order.regime,
                    )
                )
            else:
                remaining_sell_qty = qty
                exit_slippage_per_unit = (slippage_val / qty) if qty > 0 else Decimal("0")
                while remaining_sell_qty > 0 and buy_lots:
                    oldest_lot = buy_lots[0]
                    match_qty = min(oldest_lot.remaining_qty, remaining_sell_qty)
                    buy_fee_portion = oldest_lot.fee_per_unit * match_qty
                    sell_fee_portion = (fee_val / qty * match_qty) if qty > 0 else Decimal("0")
                    entry_slippage_portion = oldest_lot.slippage_per_unit * match_qty
                    exit_slippage_portion = exit_slippage_per_unit * match_qty
                    total_matched_slippage = entry_slippage_portion + exit_slippage_portion

                    matched_trades.append(
                        Trade.create(
                            ticker_symbol=ticker_symbol,
                            entry_order_uuid=oldest_lot.order_uuid,
                            exit_order_uuid=order.uuid,
                            entry_price=oldest_lot.buy_price,
                            exit_price=fill_price_val,
                            quantity=match_qty,
                            entry_fee=buy_fee_portion,
                            exit_fee=sell_fee_portion,
                            entry_timestamp=oldest_lot.entry_timestamp,
                            exit_timestamp=exec_dt.timestamp(),
                            slippage=total_matched_slippage,
                            commit_hash=order.commit_hash or oldest_lot.commit_hash,
                            winning_strategy=oldest_lot.winning_strategy or order.winning_strategy,
                            strategy_votes=oldest_lot.strategy_votes or order.strategy_votes,
                            entry_strategy_attributions=oldest_lot.strategy_attributions,
                            exit_strategy_attributions=order.strategy_attributions,
                            exit_winning_strategy=order.winning_strategy,
                            entry_regime=oldest_lot.regime,
                            exit_regime=order.regime,
                        )
                    )
                    oldest_lot.remaining_qty -= match_qty
                    remaining_sell_qty -= match_qty
                    if oldest_lot.remaining_qty <= 0:
                        buy_lots.popleft()

                if remaining_sell_qty > 0:
                    unmatched_exit_quantity += remaining_sell_qty
                    unmatched_exit_orders += 1

        return TradeExtractionResult(
            trades=matched_trades,
            unmatched_exit_quantity=unmatched_exit_quantity,
            unmatched_exit_orders=unmatched_exit_orders,
        )

    @classmethod
    def extract_trades(cls, ticker_symbol: str, orders: List[Order]) -> List[Trade]:
        return cls.extract_trades_with_audit(ticker_symbol, orders).trades

    @staticmethod
    def _calculate_open_lots_pnl(buy_lots: Deque[BuyLot], mark_price: Decimal) -> Decimal:
        unrealized = Decimal("0")
        for lot in buy_lots:
            if lot.remaining_qty <= Decimal("0"):
                continue
            unit_net = (mark_price - lot.buy_price) - lot.fee_per_unit - lot.slippage_per_unit
            unrealized += unit_net * lot.remaining_qty
        return unrealized

    @classmethod
    def compute_metrics(  # pylint: disable=too-many-locals,too-many-statements,too-many-branches
            cls,
            ticker_symbol: str,
            start: datetime,
            end: datetime,
            orders: List[Order],
            runtime_snapshot: Optional[AssetRuntimeSnapshot] = None,
    ) -> AssetPerformanceResponse:
        # Sort chronologically by execution time
        def get_exec_dt(o: Order) -> datetime:
            if o.executed_time is not None:
                return datetime.fromtimestamp(o.executed_time, tz=timezone.utc)
            return datetime.fromtimestamp(o.created_time, tz=timezone.utc)

        sorted_orders = sorted(orders, key=get_exec_dt)

        buy_lots: Deque[BuyLot] = collections.deque()

        total_volume = Decimal("0")
        total_fees = Decimal("0")
        total_realized_pnl = Decimal("0")

        buy_count = 0
        sell_count = 0
        winning_trades = 0
        losing_trades = 0
        gross_profit = Decimal("0")
        gross_loss = Decimal("0")

        daily_buckets: Dict[str, Dict[str, Any]] = collections.defaultdict(
            lambda: {"trades": 0, "volume": Decimal("0"), "fees": Decimal("0"), "realized_pnl": Decimal("0")}
        )

        matched_trades: List[Trade] = []
        execution_items: List[TradeExecutionItem] = []
        fill_steps: List[FillEquityStep] = []

        for order in sorted_orders:
            action_raw = order.trade_action.value
            side = "BUY" if "BUY" in action_raw.upper() else "SELL"

            qty = Decimal(str(order.quantity or "0"))
            fill_price_val = Decimal(str(order.fill_price or order.price or "0"))
            fee_val = Decimal(str(order.fees or "0"))
            slippage_val = Decimal(str(order.slippage or "0"))

            order_volume = (qty * fill_price_val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_volume += order_volume
            total_fees += fee_val

            exec_dt = get_exec_dt(order)
            date_str = exec_dt.strftime("%Y-%m-%d")
            daily_buckets[date_str]["trades"] += 1
            daily_buckets[date_str]["volume"] += order_volume
            daily_buckets[date_str]["fees"] += fee_val

            order_realized_pnl: Optional[Decimal] = None

            if side == "BUY":
                buy_count += 1
                fee_per_unit = (fee_val / qty) if qty > 0 else Decimal("0")
                slippage_per_unit = (slippage_val / qty) if qty > 0 else Decimal("0")
                buy_lots.append(
                    BuyLot(
                        order_uuid=order.uuid,
                        remaining_qty=qty,
                        buy_price=fill_price_val,
                        fee_per_unit=fee_per_unit,
                        entry_timestamp=exec_dt.timestamp(),
                        slippage_per_unit=slippage_per_unit,
                        commit_hash=order.commit_hash,
                        winning_strategy=order.winning_strategy,
                        strategy_votes=order.strategy_votes,
                        strategy_attributions=order.strategy_attributions,
                        regime=order.regime,
                    )
                )
            else:
                sell_count += 1
                remaining_sell_qty = qty
                sell_pnl = Decimal("0")
                exit_slippage_per_unit = (slippage_val / qty) if qty > 0 else Decimal("0")

                while remaining_sell_qty > 0 and buy_lots:
                    oldest_lot = buy_lots[0]
                    match_qty = min(oldest_lot.remaining_qty, remaining_sell_qty)

                    gross_gain = (fill_price_val - oldest_lot.buy_price) * match_qty
                    buy_fee_portion = oldest_lot.fee_per_unit * match_qty
                    sell_fee_portion = (fee_val / qty * match_qty) if qty > 0 else Decimal("0")
                    entry_slippage_portion = oldest_lot.slippage_per_unit * match_qty
                    exit_slippage_portion = exit_slippage_per_unit * match_qty
                    total_matched_slippage = entry_slippage_portion + exit_slippage_portion

                    lot_net_pnl = gross_gain - buy_fee_portion - sell_fee_portion - total_matched_slippage
                    sell_pnl += lot_net_pnl

                    if lot_net_pnl > 0:
                        gross_profit += lot_net_pnl
                        winning_trades += 1
                    elif lot_net_pnl < 0:
                        gross_loss += abs(lot_net_pnl)
                        losing_trades += 1

                    trade_obj = Trade.create(
                        ticker_symbol=ticker_symbol,
                        entry_order_uuid=oldest_lot.order_uuid,
                        exit_order_uuid=order.uuid,
                        entry_price=oldest_lot.buy_price,
                        exit_price=fill_price_val,
                        quantity=match_qty,
                        entry_fee=buy_fee_portion,
                        exit_fee=sell_fee_portion,
                        entry_timestamp=oldest_lot.entry_timestamp,
                        exit_timestamp=exec_dt.timestamp(),
                        slippage=total_matched_slippage,
                        commit_hash=order.commit_hash or oldest_lot.commit_hash,
                        winning_strategy=oldest_lot.winning_strategy or order.winning_strategy,
                        strategy_votes=oldest_lot.strategy_votes or order.strategy_votes,
                        entry_strategy_attributions=oldest_lot.strategy_attributions,
                        exit_strategy_attributions=order.strategy_attributions,
                        exit_winning_strategy=order.winning_strategy,
                        entry_regime=oldest_lot.regime,
                        exit_regime=order.regime,
                    )
                    matched_trades.append(trade_obj)

                    oldest_lot.remaining_qty -= match_qty
                    remaining_sell_qty -= match_qty

                    if oldest_lot.remaining_qty <= 0:
                        buy_lots.popleft()

                order_realized_pnl = sell_pnl.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                total_realized_pnl += order_realized_pnl
                daily_buckets[date_str]["realized_pnl"] += order_realized_pnl

            open_lots_pnl = cls._calculate_open_lots_pnl(buy_lots, fill_price_val)
            step_pnl = (total_realized_pnl + open_lots_pnl).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            fill_steps.append(
                FillEquityStep(timestamp=exec_dt.timestamp(), cumulative_pnl=step_pnl)
            )

            execution_items.append(
                TradeExecutionItem(
                    order_id=order.uuid,
                    timestamp=exec_dt.isoformat(),
                    side=side,
                    price=str(order.price),
                    fill_price=str(fill_price_val),
                    quantity=str(qty),
                    fees=f"{fee_val:.4f}",
                    realized_pnl=f"{order_realized_pnl:+.2f}" if order_realized_pnl is not None else None,
                )
            )

        total_closed_trades = winning_trades + losing_trades
        win_rate = round(float((winning_trades / total_closed_trades) * 100), 2) if total_closed_trades > 0 else 0.0

        if gross_loss > 0:
            profit_factor = round(float(gross_profit / gross_loss), 2)
        elif gross_profit > 0:
            profit_factor = 999.0
        else:
            profit_factor = 0.0

        avg_trade_pnl = (
            (total_realized_pnl / total_closed_trades).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if total_closed_trades > 0
            else Decimal("0.00")
        )

        daily_list = [
            DailyPerformance(
                date=d,
                trades=data["trades"],
                volume=f"{data['volume']:.2f}",
                fees=f"{data['fees']:.4f}",
                realized_pnl=f"{data['realized_pnl']:+.2f}",
            )
            for d, data in sorted(daily_buckets.items())
        ]

        summary = PerformanceSummary(
            trades=len(sorted_orders),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            volume=f"{total_volume:.2f}",
            fees=f"{total_fees:.4f}",
            realized_pnl=f"{total_realized_pnl:+.2f}",
            average_trade_pnl=f"{avg_trade_pnl:+.2f}",
            profit_factor=profit_factor,
            buy_count=buy_count,
            sell_count=sell_count,
        )

        strategy_attribution = TradeAttributionService.attribute_by_strategy(matched_trades)
        strategy_attribution_models = {
            strat: StrategyAttributionModel.from_attribution_metrics(metrics)
            for strat, metrics in strategy_attribution.items()
        }

        commit_attribution = TradeAttributionService.attribute_by_commit(matched_trades)
        commit_attribution_models = {
            c_hash: StrategyAttributionModel.from_attribution_metrics(metrics)
            for c_hash, metrics in commit_attribution.items()
        }

        # 4 Dimensions of Strategy Robustness Metrics
        end_mark_price = Decimal("0")
        if (
            runtime_snapshot is not None
            and runtime_snapshot.latest_price is not None
            and Decimal(str(runtime_snapshot.latest_price)) > Decimal("0")
        ):
            end_mark_price = Decimal(str(runtime_snapshot.latest_price))
        elif sorted_orders:
            last_order = sorted_orders[-1]
            end_mark_price = Decimal(str(last_order.fill_price or last_order.price or "0"))

        end_open_lots_pnl = (
            cls._calculate_open_lots_pnl(buy_lots, end_mark_price)
            if end_mark_price > Decimal("0")
            else Decimal("0")
        )
        total_period_pnl = (total_realized_pnl + end_open_lots_pnl).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        initial_balance, mark_to_market_equity = cls._resolve_live_balances(
            runtime_snapshot=runtime_snapshot,
            sorted_orders=sorted_orders,
            total_period_pnl=total_period_pnl,
        )
        current_equity = initial_balance
        peak_equity = initial_balance
        max_dd = Decimal("0")
        max_dd_pct = Decimal("0")

        snapshots: list[PortfolioSnapshot] = [
            PortfolioSnapshot(
                timestamp=int(start.timestamp()),
                cash=initial_balance,
                positions={},
                equity=initial_balance,
            )
        ]

        for step in fill_steps:
            current_equity = (initial_balance + step.cumulative_pnl).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            peak_equity = max(peak_equity, current_equity)
            dd = peak_equity - current_equity
            max_dd = max(max_dd, dd)
            if peak_equity > Decimal("0"):
                dd_pct = (dd / peak_equity) * Decimal("100")
                max_dd_pct = max(max_dd_pct, dd_pct)
            snapshots.append(
                PortfolioSnapshot(
                    timestamp=int(step.timestamp),
                    cash=current_equity,
                    positions={},
                    equity=current_equity,
                )
            )

        if mark_to_market_equity is not None:
            current_equity = mark_to_market_equity
            peak_equity = max(peak_equity, current_equity)
            dd = peak_equity - current_equity
            max_dd = max(max_dd, dd)
            if peak_equity > Decimal("0"):
                dd_pct = (dd / peak_equity) * Decimal("100")
                max_dd_pct = max(max_dd_pct, dd_pct)
            avail_cash = (
                Decimal(str(runtime_snapshot.available_balance)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if runtime_snapshot and runtime_snapshot.available_balance is not None
                else current_equity
            )
            snapshots.append(
                PortfolioSnapshot(
                    timestamp=int(end.timestamp()),
                    cash=avail_cash,
                    positions={},
                    equity=current_equity,
                )
            )

        equity_curve = cls._build_equity_curve(
            start=start,
            end=end,
            initial_balance=initial_balance,
            fill_steps=fill_steps,
            mark_to_market_equity=mark_to_market_equity,
        )

        fills: list[BacktestFill] = []
        for o in sorted_orders:
            action = (
                o.trade_action
                if hasattr(o.trade_action, "value")
                else (TradeAction.BUY if "BUY" in str(o.trade_action).upper() else TradeAction.SELL)
            )
            qty = Decimal(str(o.quantity or "0"))
            fill_p = Decimal(str(o.fill_price or o.price or "0"))
            req_p = Decimal(str(o.price or fill_p))
            fee_val = Decimal(str(o.fees or "0"))
            slip_val = Decimal(str(o.slippage or "0"))
            slip_unit = (slip_val / qty) if qty > Decimal("0") else Decimal("0")
            exec_t = float(o.executed_time or o.created_time or 0.0)
            created_t = float(o.created_time or exec_t)

            fills.append(
                BacktestFill(
                    order_uuid=o.uuid,
                    ticker_symbol=ticker_symbol,
                    trade_action=action,
                    requested_price=req_p,
                    market_price=req_p,
                    execution_price=fill_p,
                    quantity=qty,
                    fee=fee_val,
                    slippage_per_unit=slip_unit,
                    slippage_cost=slip_val,
                    submitted_at=created_t,
                    executed_at=exec_t,
                )
            )

        bt_result = BacktestResult(
            session_id="live-performance",
            ticker_symbol=ticker_symbol,
            initial_balance=initial_balance,
            final_balance=current_equity,
            final_equity=current_equity,
            execution=ExecutionConfiguration(),
            orders=sorted_orders,
            fills=fills,
            portfolio_snapshots=snapshots,
            trades=matched_trades,
        )

        risk_adjusted = RiskAdjustedCalculator().calculate(
            snapshots=snapshots,
            initial_balance=initial_balance,
            final_equity=current_equity,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
        )
        behavior = TradingBehaviorCalculator().calculate(
            fills=fills,
            snapshots=snapshots,
            initial_balance=initial_balance,
        )
        execution = ExecutionQualityCalculator().calculate(fills=fills, orders=sorted_orders)
        portfolio = PortfolioRiskCalculator().calculate(result=bt_result)

        return AssetPerformanceResponse(
            ticker_symbol=ticker_symbol,
            period=PeriodModel(start=start.isoformat(), end=end.isoformat()),
            summary=summary,
            daily=daily_list,
            trades=execution_items,
            equity_curve=equity_curve,
            starting_balance=f"{initial_balance:.2f}",
            current_equity=f"{current_equity:.2f}",
            strategy_attribution=strategy_attribution_models,
            commit_attribution=commit_attribution_models,
            risk_adjusted=risk_adjusted,
            behavior=behavior,
            execution=execution,
            portfolio=portfolio,
        )

    @staticmethod
    def _estimate_capital_from_orders(sorted_orders: List[Order]) -> Decimal:
        net_cash_deployed = Decimal("0")
        peak_deployed = Decimal("0")
        max_order_notional = Decimal("0")

        for order in sorted_orders:
            action_raw = order.trade_action.value
            side = "BUY" if "BUY" in action_raw.upper() else "SELL"
            qty = Decimal(str(order.quantity or "0"))
            fill_price = Decimal(str(order.fill_price or order.price or "0"))
            fee = Decimal(str(order.fees or "0"))
            notional = qty * fill_price
            max_order_notional = max(max_order_notional, notional + fee)

            if side == "BUY":
                net_cash_deployed += notional + fee
                peak_deployed = max(peak_deployed, net_cash_deployed)
            else:
                net_cash_deployed = max(Decimal("0"), net_cash_deployed - (notional - fee))

        candidate = peak_deployed if peak_deployed > Decimal("0") else max_order_notional
        return candidate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @classmethod
    def _resolve_live_balances(
            cls,
            runtime_snapshot: Optional[AssetRuntimeSnapshot],
            sorted_orders: List[Order],
            total_period_pnl: Decimal,
    ) -> tuple[Decimal, Optional[Decimal]]:
        if runtime_snapshot is None:
            return cls._estimate_capital_from_orders(sorted_orders), None

        mark_to_market_equity: Optional[Decimal] = None
        if runtime_snapshot.available_balance is not None:
            avail = Decimal(str(runtime_snapshot.available_balance))
            pos_qty = Decimal(str(runtime_snapshot.position_quantity or 0.0))
            if (
                runtime_snapshot.latest_price is not None
                and Decimal(str(runtime_snapshot.latest_price)) > Decimal("0")
            ):
                price = Decimal(str(runtime_snapshot.latest_price))
            elif pos_qty > Decimal("0") and sorted_orders:
                last_order = sorted_orders[-1]
                price = Decimal(str(last_order.fill_price or last_order.price or "0"))
            else:
                price = Decimal("0")
            mark_to_market_equity = (avail + pos_qty * price).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        if mark_to_market_equity is not None and mark_to_market_equity > Decimal("0"):
            derived = (mark_to_market_equity - total_period_pnl).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if derived > Decimal("0"):
                initial_balance = derived
            elif (
                runtime_snapshot.starting_balance is not None
                and Decimal(str(runtime_snapshot.starting_balance)) > Decimal("0")
            ):
                initial_balance = Decimal(str(runtime_snapshot.starting_balance)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                initial_balance = mark_to_market_equity
        elif (
            runtime_snapshot.starting_balance is not None
            and Decimal(str(runtime_snapshot.starting_balance)) > Decimal("0")
        ):
            initial_balance = Decimal(str(runtime_snapshot.starting_balance)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            mark_to_market_equity = (initial_balance + total_period_pnl).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            initial_balance = cls._estimate_capital_from_orders(sorted_orders)

        return initial_balance, mark_to_market_equity

    @classmethod
    def _make_equity_point(
            cls,
            timestamp_iso: str,
            initial_balance: Decimal,
            current_equity: Decimal,
            peak_equity: Decimal,
    ) -> AssetEquityPointModel:
        rounded_pnl = (current_equity - initial_balance).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        dd = peak_equity - current_equity
        dd_pct = (
            round(float((dd / peak_equity) * Decimal("100")), 2)
            if peak_equity > Decimal("0")
            else 0.0
        )
        return AssetEquityPointModel(
            timestamp=timestamp_iso,
            equity=f"{current_equity:.2f}",
            cumulative_pnl=f"{rounded_pnl:+.2f}",
            drawdown_pct=dd_pct,
        )

    @classmethod
    def _upsert_equity_point(
            cls,
            curve: List[AssetEquityPointModel],
            point: AssetEquityPointModel,
    ) -> None:
        if curve and curve[-1].timestamp == point.timestamp:
            curve[-1] = point
        else:
            curve.append(point)

    @classmethod
    def _build_equity_curve(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            cls,
            start: datetime,
            end: datetime,
            initial_balance: Decimal,
            fill_steps: List[FillEquityStep],
            mark_to_market_equity: Optional[Decimal] = None,
    ) -> List[AssetEquityPointModel]:
        if not fill_steps and mark_to_market_equity is None:
            return []

        curve: List[AssetEquityPointModel] = [
            cls._make_equity_point(
                start.isoformat(), initial_balance, initial_balance, initial_balance
            )
        ]

        peak_equity = initial_balance

        for step in fill_steps:
            current_equity = (initial_balance + step.cumulative_pnl).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            peak_equity = max(peak_equity, current_equity)
            fill_iso = datetime.fromtimestamp(step.timestamp, tz=timezone.utc).isoformat()
            cls._upsert_equity_point(
                curve,
                cls._make_equity_point(fill_iso, initial_balance, current_equity, peak_equity),
            )

        if mark_to_market_equity is not None:
            peak_equity = max(peak_equity, mark_to_market_equity)
            cls._upsert_equity_point(
                curve,
                cls._make_equity_point(
                    end.isoformat(), initial_balance, mark_to_market_equity, peak_equity
                ),
            )

        return curve
