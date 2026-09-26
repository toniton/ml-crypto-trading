from __future__ import annotations

import collections
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Deque, Dict, List, Optional

from pydantic import BaseModel

from api.interfaces.order import Order
from api.interfaces.trade import Trade
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository
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
    strategy_attribution: Dict[str, StrategyAttributionModel] = {}
    commit_attribution: Dict[str, StrategyAttributionModel] = {}


class BuyLot:
    def __init__(
            self,
            order_uuid: str,
            remaining_qty: Decimal,
            buy_price: Decimal,
            fee_per_unit: Decimal,
            entry_timestamp: float,
            commit_hash: Optional[str] = None,
            winning_strategy: Optional[str] = None,
            strategy_votes: Optional[dict[str, str]] = None,
    ) -> None:
        self.order_uuid = order_uuid
        self.remaining_qty = remaining_qty
        self.buy_price = buy_price
        self.fee_per_unit = fee_per_unit
        self.entry_timestamp = entry_timestamp
        self.commit_hash = commit_hash
        self.winning_strategy = winning_strategy
        self.strategy_votes = strategy_votes


class AssetPerformanceService:
    def __init__(self, database_manager: DatabaseManager) -> None:
        self._database_manager = database_manager

    def calculate_performance(
            self,
            ticker_symbol: str,
            start: datetime,
            end: datetime,
    ) -> AssetPerformanceResponse:
        orders = self._fetch_completed_orders(ticker_symbol, start, end)
        return self.compute_metrics(ticker_symbol, start, end, orders)

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
    def extract_trades(cls, ticker_symbol: str, orders: List[Order]) -> List[Trade]:  # pylint: disable=too-many-locals
        def get_exec_dt(o: Order) -> datetime:
            if o.executed_time is not None:
                return datetime.fromtimestamp(o.executed_time, tz=timezone.utc)
            return datetime.fromtimestamp(o.created_time, tz=timezone.utc)

        sorted_orders = sorted(orders, key=get_exec_dt)
        buy_lots: Deque[BuyLot] = collections.deque()
        matched_trades: List[Trade] = []

        for order in sorted_orders:
            action_raw = order.trade_action.value
            side = "BUY" if "BUY" in action_raw.upper() else "SELL"
            qty = Decimal(str(order.quantity or "0"))
            fill_price_val = Decimal(str(order.fill_price or order.price or "0"))
            fee_val = Decimal(str(order.fees or "0"))
            exec_dt = get_exec_dt(order)

            if side == "BUY":
                fee_per_unit = (fee_val / qty) if qty > 0 else Decimal("0")
                buy_lots.append(
                    BuyLot(
                        order_uuid=order.uuid,
                        remaining_qty=qty,
                        buy_price=fill_price_val,
                        fee_per_unit=fee_per_unit,
                        entry_timestamp=exec_dt.timestamp(),
                        commit_hash=order.commit_hash,
                        winning_strategy=order.winning_strategy,
                        strategy_votes=order.strategy_votes,
                    )
                )
            else:
                remaining_sell_qty = qty
                while remaining_sell_qty > 0 and buy_lots:
                    oldest_lot = buy_lots[0]
                    match_qty = min(oldest_lot.remaining_qty, remaining_sell_qty)
                    buy_fee_portion = oldest_lot.fee_per_unit * match_qty
                    sell_fee_portion = (fee_val / qty * match_qty) if qty > 0 else Decimal("0")

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
                            commit_hash=order.commit_hash or oldest_lot.commit_hash,
                            winning_strategy=order.winning_strategy or oldest_lot.winning_strategy,
                            strategy_votes=order.strategy_votes or oldest_lot.strategy_votes,
                        )
                    )
                    oldest_lot.remaining_qty -= match_qty
                    remaining_sell_qty -= match_qty
                    if oldest_lot.remaining_qty <= 0:
                        buy_lots.popleft()

        return matched_trades

    @classmethod
    def compute_metrics(  # pylint: disable=too-many-locals,too-many-statements
            cls,
            ticker_symbol: str,
            start: datetime,
            end: datetime,
            orders: List[Order],
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

        for order in sorted_orders:
            action_raw = order.trade_action.value
            side = "BUY" if "BUY" in action_raw.upper() else "SELL"

            qty = Decimal(str(order.quantity or "0"))
            fill_price_val = Decimal(str(order.fill_price or order.price or "0"))
            fee_val = Decimal(str(order.fees or "0"))

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
                buy_lots.append(
                    BuyLot(
                        order_uuid=order.uuid,
                        remaining_qty=qty,
                        buy_price=fill_price_val,
                        fee_per_unit=fee_per_unit,
                        entry_timestamp=exec_dt.timestamp(),
                        commit_hash=order.commit_hash,
                        winning_strategy=order.winning_strategy,
                        strategy_votes=order.strategy_votes,
                    )
                )
            else:
                sell_count += 1
                remaining_sell_qty = qty
                sell_pnl = Decimal("0")

                while remaining_sell_qty > 0 and buy_lots:
                    oldest_lot = buy_lots[0]
                    match_qty = min(oldest_lot.remaining_qty, remaining_sell_qty)

                    gross_gain = (fill_price_val - oldest_lot.buy_price) * match_qty
                    buy_fee_portion = oldest_lot.fee_per_unit * match_qty
                    sell_fee_portion = (fee_val / qty * match_qty) if qty > 0 else Decimal("0")

                    lot_net_pnl = gross_gain - buy_fee_portion - sell_fee_portion
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
                        commit_hash=order.commit_hash or oldest_lot.commit_hash,
                        winning_strategy=order.winning_strategy or oldest_lot.winning_strategy,
                        strategy_votes=order.strategy_votes or oldest_lot.strategy_votes,
                    )
                    matched_trades.append(trade_obj)

                    oldest_lot.remaining_qty -= match_qty
                    remaining_sell_qty -= match_qty

                    if oldest_lot.remaining_qty <= 0:
                        buy_lots.popleft()

                order_realized_pnl = sell_pnl.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                total_realized_pnl += order_realized_pnl
                daily_buckets[date_str]["realized_pnl"] += order_realized_pnl

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
                date=day_key,
                trades=data["trades"],
                volume=f"{data['volume']:.2f}",
                fees=f"{data['fees']:.4f}",
                realized_pnl=f"{data['realized_pnl']:+.2f}",
            )
            for day_key, data in sorted(daily_buckets.items())
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

        raw_strategy_attribution = TradeAttributionService.attribute_by_strategy(matched_trades)
        raw_commit_attribution = TradeAttributionService.attribute_by_commit(matched_trades)

        strategy_attribution = {
            k: StrategyAttributionModel.from_attribution_metrics(v)
            for k, v in raw_strategy_attribution.items()
        }
        commit_attribution = {
            k: StrategyAttributionModel.from_attribution_metrics(v)
            for k, v in raw_commit_attribution.items()
        }

        return AssetPerformanceResponse(
            ticker_symbol=ticker_symbol,
            period=PeriodModel(
                start=start.isoformat(),
                end=end.isoformat(),
            ),
            summary=summary,
            daily=daily_list,
            trades=execution_items,
            strategy_attribution=strategy_attribution,
            commit_attribution=commit_attribution,
        )
