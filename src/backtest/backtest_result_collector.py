from decimal import Decimal

from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.trade import Trade
from api.interfaces.trade_action import TradeAction
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.domain.result import (
    BacktestFill,
    BacktestResult,
    PortfolioSnapshot,
)
from src.backtest.domain.session import BacktestSession
from src.backtest.events.domain_events import (
    OrderFilledEvent,
    OrderSubmittedEvent,
    PortfolioSnapshotEvent,
)
from src.trading.analytics.trade_attribution_service import TradeAttributionService
from src.trading.events.domain_events import MarketDataEvent, TradeClosedEvent


class BacktestResultCollector:
    def __init__(self, bus: BacktestEventBus):
        self._market_series: list[MarketData] = []
        self._snapshots: list[PortfolioSnapshot] = []
        self._orders: list[Order] = []
        self._orders_by_uuid: dict[str, Order] = {}
        self._fills: list[BacktestFill] = []
        self._trades: list[Trade] = []

        bus.subscribe_callback(MarketDataEvent, self._on_market_data)
        bus.subscribe_callback(PortfolioSnapshotEvent, self._on_snapshot)
        bus.subscribe_callback(OrderSubmittedEvent, self._on_order_submitted)
        bus.subscribe_callback(OrderFilledEvent, self._on_fill)
        bus.subscribe_callback(TradeClosedEvent, self._on_trade_closed)

    def _on_market_data(self, event: MarketDataEvent) -> None:
        self._market_series.append(event.market_data)

    def _on_snapshot(self, event: PortfolioSnapshotEvent) -> None:
        self._snapshots.append(event.snapshot)

    def _on_order_submitted(self, event: OrderSubmittedEvent) -> None:
        self._orders.append(event.order)
        self._orders_by_uuid[event.order.uuid] = event.order

    def _on_fill(self, event: OrderFilledEvent) -> None:
        if event.execution is not None:
            self._fills.append(self._to_fill(event.execution))

    def _on_trade_closed(self, event: TradeClosedEvent) -> None:
        self._trades.append(event.trade)

    def build_result(self, session: BacktestSession) -> BacktestResult:
        request = session.request
        initial_balance = request.initial_balance
        final_balance = self._snapshots[-1].cash if self._snapshots else initial_balance
        final_equity = self._snapshots[-1].equity if self._snapshots else final_balance

        trades = list(self._trades)
        if not trades and self._fills:
            trades = self._match_trades_from_fills(
                fills=self._fills,
                orders_by_uuid=self._orders_by_uuid,
                ticker_symbol=request.ticker_symbol,
            )
            self._trades = trades

        strategy_attribution = TradeAttributionService.attribute_by_strategy(trades)
        commit_attribution = TradeAttributionService.attribute_by_commit(trades)

        return BacktestResult(
            session_id=session.id,
            ticker_symbol=request.ticker_symbol,
            initial_balance=initial_balance,
            final_balance=final_balance,
            final_equity=final_equity,
            execution=request.execution,
            orders=list(self._orders),
            fills=list(self._fills),
            portfolio_snapshots=list(self._snapshots),
            market_series=list(self._market_series),
            trades=trades,
            strategy_attribution=strategy_attribution,
            commit_attribution=commit_attribution,
        )

    @staticmethod
    def _to_fill(result) -> BacktestFill:
        return BacktestFill(
            order_uuid=result.order_uuid,
            ticker_symbol=result.ticker_symbol,
            trade_action=result.trade_action,
            requested_price=result.requested_price,
            market_price=result.market_price,
            execution_price=result.execution_price,
            quantity=result.executed_quantity,
            fee=result.fee,
            slippage_per_unit=result.slippage_per_unit,
            slippage_cost=result.slippage_cost,
            submitted_at=result.submitted_at,
            executed_at=result.executed_at,
        )

    @staticmethod
    def _match_trades_from_fills(  # pylint: disable=too-many-locals
            fills: list[BacktestFill],
            orders_by_uuid: dict[str, Order],
            ticker_symbol: str,
    ) -> list[Trade]:
        buy_lots: list[list] = []
        matched_trades: list[Trade] = []

        for fill in fills:
            order = orders_by_uuid.get(fill.order_uuid)
            commit = order.commit_hash if order else None
            winning_strat = order.winning_strategy if order else None
            strat_votes = order.strategy_votes if order else None

            if fill.trade_action == TradeAction.BUY:
                fee_per_unit = (fill.fee / fill.quantity) if fill.quantity > Decimal(0) else Decimal(0)
                buy_lots.append([
                    fill.order_uuid,
                    fill.quantity,
                    fill.execution_price,
                    fee_per_unit,
                    fill.executed_at,
                    commit,
                    winning_strat,
                    strat_votes,
                ])
            elif fill.trade_action == TradeAction.SELL:
                sell_qty = fill.quantity
                sell_price = fill.execution_price
                sell_fee_per_unit = (fill.fee / fill.quantity) if fill.quantity > Decimal(0) else Decimal(0)

                while sell_qty > Decimal(0) and buy_lots:
                    lot = buy_lots[0]
                    matched_qty = min(sell_qty, lot[1])
                    buy_fee_unit = lot[3]

                    trade = Trade.create(
                        ticker_symbol=ticker_symbol,
                        entry_order_uuid=lot[0],
                        exit_order_uuid=fill.order_uuid,
                        entry_price=lot[2],
                        exit_price=sell_price,
                        quantity=matched_qty,
                        entry_fee=buy_fee_unit * matched_qty,
                        exit_fee=sell_fee_per_unit * matched_qty,
                        entry_timestamp=lot[4],
                        exit_timestamp=fill.executed_at,
                        slippage=fill.slippage_cost,
                        commit_hash=commit or lot[5],
                        winning_strategy=winning_strat or lot[6],
                        strategy_votes=strat_votes or lot[7],
                    )
                    matched_trades.append(trade)

                    lot[1] -= matched_qty
                    sell_qty -= matched_qty
                    if lot[1] <= Decimal(0):
                        buy_lots.pop(0)

        return matched_trades
