from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from api.interfaces.trade import Trade


# pylint: disable=too-many-instance-attributes,duplicate-code
@dataclass(frozen=True)
class AttributionMetrics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    break_even_trades: int
    win_rate_pct: float
    gross_pnl: Decimal
    total_fees: Decimal
    total_slippage: Decimal
    net_pnl: Decimal
    profit_factor: float
    avg_return_pct: float
    avg_duration_seconds: float
    max_win: Decimal
    max_loss: Decimal


class TradeAttributionService:
    """Calculates multidimensional P&L attribution and execution statistics across trades."""

    @classmethod
    def calculate_metrics(cls, trades: list[Trade]) -> AttributionMetrics:
        if not trades:
            return cls._empty_metrics()

        total = len(trades)
        wins, losses, break_even, win_rate = cls._compute_outcome_counts(trades, total)
        pnl = cls._compute_pnl_totals(trades)
        stats = cls._compute_summary_stats(trades, total)

        return AttributionMetrics(
            total_trades=total,
            winning_trades=wins,
            losing_trades=losses,
            break_even_trades=break_even,
            win_rate_pct=win_rate,
            gross_pnl=pnl[0],
            total_fees=pnl[1],
            total_slippage=pnl[2],
            net_pnl=pnl[3],
            profit_factor=cls._compute_profit_factor(trades),
            avg_return_pct=stats[0],
            avg_duration_seconds=stats[1],
            max_win=stats[2],
            max_loss=stats[3],
        )

    @staticmethod
    def _compute_outcome_counts(trades: list[Trade], total: int) -> tuple[int, int, int, float]:
        wins = sum(1 for t in trades if t.net_pnl > Decimal(0))
        losses = sum(1 for t in trades if t.net_pnl < Decimal(0))
        break_even = sum(1 for t in trades if t.net_pnl == Decimal(0))
        win_rate = round((wins / total * 100.0) if total > 0 else 0.0, 2)
        return wins, losses, break_even, win_rate

    @staticmethod
    def _compute_pnl_totals(trades: list[Trade]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        gross = sum((t.gross_pnl for t in trades), Decimal(0))
        fees = sum((t.fees for t in trades), Decimal(0))
        slippage = sum((t.slippage for t in trades), Decimal(0))
        net = sum((t.net_pnl for t in trades), Decimal(0))
        return gross, fees, slippage, net

    @staticmethod
    def _compute_profit_factor(trades: list[Trade]) -> float:
        gross_wins = sum((t.net_pnl for t in trades if t.net_pnl > Decimal(0)), Decimal(0))
        gross_losses = abs(sum((t.net_pnl for t in trades if t.net_pnl < Decimal(0)), Decimal(0)))
        if gross_losses > Decimal(0):
            return round(float(gross_wins / gross_losses), 2)
        if gross_wins > Decimal(0):
            return 999.99
        return 0.0

    @staticmethod
    def _compute_summary_stats(trades: list[Trade], total: int) -> tuple[float, float, Decimal, Decimal]:
        avg_ret = round(float(sum((t.return_pct for t in trades), Decimal(0)) / Decimal(total)), 4)
        avg_dur = round(sum(t.duration_seconds for t in trades) / total, 2)
        max_win = max((t.net_pnl for t in trades), default=Decimal(0))
        max_loss = min((t.net_pnl for t in trades), default=Decimal(0))
        return avg_ret, avg_dur, max_win, max_loss

    @classmethod
    def attribute_by_commit(cls, trades: list[Trade]) -> dict[str, AttributionMetrics]:
        grouped: dict[str, list[Trade]] = defaultdict(list)
        for trade in trades:
            commit = trade.commit_hash or "UNKNOWN"
            grouped[commit].append(trade)
        return {commit: cls.calculate_metrics(group) for commit, group in grouped.items()}

    @classmethod
    def attribute_by_strategy(cls, trades: list[Trade]) -> dict[str, AttributionMetrics]:
        grouped: dict[str, list[Trade]] = defaultdict(list)
        for trade in trades:
            strats: set[str] = set()
            if trade.entry_strategy_attributions:
                strats.update(s for s, w in trade.entry_strategy_attributions.items() if w > 0)
            elif trade.winning_strategy:
                strats.add(trade.winning_strategy)

            if trade.exit_strategy_attributions:
                strats.update(s for s, w in trade.exit_strategy_attributions.items() if w > 0)
            elif trade.exit_winning_strategy:
                strats.add(trade.exit_winning_strategy)

            if not strats:
                strats.add("UNKNOWN")

            for strategy in strats:
                grouped[strategy].append(trade)
        return {strategy: cls.calculate_metrics(group) for strategy, group in grouped.items()}

    @classmethod
    def _normalize_vote(cls, vote: Any) -> str:
        if vote is None:
            return "HOLD"
        if isinstance(vote, bool):
            return "BUY" if vote is True else "HOLD"
        s = str(vote).strip().upper()
        if s in ("TRUE", "1", "YES", "BUY", "TRADEACTION.BUY"):
            return "BUY"
        if s in ("SELL", "-1", "TRADEACTION.SELL"):
            return "SELL"
        return "HOLD"

    @classmethod
    def attribute_by_strategy_proportional(cls, trades: list[Trade]) -> dict[str, AttributionMetrics]:
        strategy_trades: dict[str, list[tuple[Trade, float]]] = defaultdict(list)
        for trade in trades:
            cls._accumulate_proportional_trade(strategy_trades, trade)

        result: dict[str, AttributionMetrics] = {}
        for strat_name, weighted_list in strategy_trades.items():
            result[strat_name] = cls._calculate_proportional_metrics(weighted_list)
        return result

    @classmethod
    def _accumulate_proportional_trade(
            cls, strategy_trades: dict[str, list[tuple[Trade, float]]], trade: Trade
    ) -> None:
        has_entry = bool(trade.entry_strategy_attributions)
        has_exit = bool(trade.exit_strategy_attributions)

        if has_entry and has_exit:
            cls._append_weighted_shares(strategy_trades, trade, trade.entry_strategy_attributions, 0.5)
            cls._append_weighted_shares(strategy_trades, trade, trade.exit_strategy_attributions, 0.5)
            return

        if has_entry:
            cls._append_single_leg_shares(strategy_trades, trade, trade.entry_strategy_attributions)
            return

        if has_exit:
            cls._append_single_leg_shares(strategy_trades, trade, trade.exit_strategy_attributions)
            return

        winning = trade.winning_strategy or trade.exit_winning_strategy or "UNATTRIBUTED"
        strategy_trades[winning].append((trade, 1.0))

    @staticmethod
    def _append_weighted_shares(
            strategy_trades: dict[str, list[tuple[Trade, float]]],
            trade: Trade,
            attributions: dict[str, float],
            scale: float,
    ) -> None:
        for strat_name, weight_share in attributions.items():
            if weight_share > 0:
                strategy_trades[strat_name].append((trade, float(weight_share) * scale))

    @staticmethod
    def _append_single_leg_shares(
            strategy_trades: dict[str, list[tuple[Trade, float]]],
            trade: Trade,
            attributions: dict[str, float],
    ) -> None:
        allocated = sum(attributions.values())
        for strat_name, weight_share in attributions.items():
            if weight_share > 0:
                strategy_trades[strat_name].append((trade, float(weight_share)))
        if allocated < 0.9999:
            strategy_trades["UNATTRIBUTED"].append((trade, max(0.0, 1.0 - allocated)))

    @classmethod
    def _extract_trade_vote_sets(cls, trade: Trade) -> list[dict[str, str]]:
        vote_sets: list[dict[str, str]] = []
        if trade.strategy_votes:
            vote_sets.append({s: cls._normalize_vote(v) for s, v in trade.strategy_votes.items()})
        elif trade.entry_strategy_attributions:
            vote_sets.append({s: "BUY" for s in trade.entry_strategy_attributions})
        elif trade.winning_strategy:
            vote_sets.append({trade.winning_strategy: "BUY"})

        if trade.exit_strategy_votes:
            vote_sets.append({s: cls._normalize_vote(v) for s, v in trade.exit_strategy_votes.items()})
        elif trade.exit_strategy_attributions:
            vote_sets.append({s: "SELL" for s in trade.exit_strategy_attributions})
        elif trade.exit_winning_strategy:
            vote_sets.append({trade.exit_winning_strategy: "SELL"})
        return vote_sets

    @staticmethod
    def _accumulate_co_voting(
            aligned_pairs: dict[str, dict[str, int]],
            agreed_pairs: dict[str, dict[str, int]],
            vote_sets: list[dict[str, str]],
    ) -> None:
        for strat_votes in vote_sets:
            strats = sorted(strat_votes.keys())
            for s1 in strats:
                v1 = strat_votes[s1]
                for s2 in strats:
                    aligned_pairs[s1][s2] += 1
                    if v1 == strat_votes[s2]:
                        agreed_pairs[s1][s2] += 1

    @staticmethod
    def _accumulate_cross_strategy_synergy(
            aligned_pairs: dict[str, dict[str, int]],
            agreed_pairs: dict[str, dict[str, int]],
            trade: Trade,
    ) -> None:
        entry_strats = (
            list(trade.entry_strategy_attributions.keys())
            if trade.entry_strategy_attributions
            else ([trade.winning_strategy] if trade.winning_strategy else [])
        )
        exit_strats = (
            list(trade.exit_strategy_attributions.keys())
            if trade.exit_strategy_attributions
            else ([trade.exit_winning_strategy] if trade.exit_winning_strategy else [])
        )
        for s_in in entry_strats:
            for s_out in exit_strats:
                aligned_pairs[s_in][s_out] += 1
                aligned_pairs[s_out][s_in] += 1
                if trade.net_pnl > Decimal(0):
                    agreed_pairs[s_in][s_out] += 1
                    agreed_pairs[s_out][s_in] += 1

    @classmethod
    def compute_co_voting_details(
            cls, trades: list[Trade]
    ) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, int]]]:
        aligned_pairs: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        agreed_pairs: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for trade in trades:
            vote_sets = cls._extract_trade_vote_sets(trade)
            cls._accumulate_co_voting(aligned_pairs, agreed_pairs, vote_sets)
            cls._accumulate_cross_strategy_synergy(aligned_pairs, agreed_pairs, trade)

        matrix: dict[str, dict[str, float]] = {}
        counts: dict[str, dict[str, int]] = {}
        for s1, targets in aligned_pairs.items():
            matrix[s1] = {}
            counts[s1] = {}
            for s2, total in targets.items():
                agreed = agreed_pairs[s1].get(s2, 0)
                matrix[s1][s2] = round(agreed / total, 4) if total > 0 else 0.0
                counts[s1][s2] = total

        return matrix, counts

    @classmethod
    def compute_co_voting_matrix(
            cls, trades: list[Trade]
    ) -> dict[str, dict[str, float]]:
        matrix, _ = cls.compute_co_voting_details(trades)
        return matrix

    @classmethod
    def attribute_by_participation(cls, trades: list[Trade]) -> dict[str, AttributionMetrics]:
        grouped: dict[str, list[Trade]] = defaultdict(list)
        for trade in trades:
            positive_strats: list[str] = []
            if trade.entry_strategy_attributions:
                positive_strats.extend(trade.entry_strategy_attributions.keys())
            elif trade.strategy_votes:
                for strat, vote in trade.strategy_votes.items():
                    if cls._normalize_vote(vote) in ("BUY", "SELL"):
                        positive_strats.append(strat)
            elif trade.winning_strategy:
                positive_strats.append(trade.winning_strategy)

            if trade.exit_strategy_attributions:
                positive_strats.extend(trade.exit_strategy_attributions.keys())
            elif trade.exit_strategy_votes:
                for strat, vote in trade.exit_strategy_votes.items():
                    if cls._normalize_vote(vote) in ("BUY", "SELL"):
                        positive_strats.append(strat)
            elif trade.exit_winning_strategy:
                positive_strats.append(trade.exit_winning_strategy)

            for strat in set(positive_strats):
                grouped[strat].append(trade)

        return {strat: cls.calculate_metrics(group) for strat, group in grouped.items()}

    @classmethod
    def attribute_by_entry_vs_exit(
            cls, trades: list[Trade]
    ) -> dict[str, dict[str, AttributionMetrics]]:
        entry_trades: dict[str, list[Trade]] = defaultdict(list)
        exit_trades: dict[str, list[Trade]] = defaultdict(list)

        for trade in trades:
            entry_strats = (
                list(trade.entry_strategy_attributions.keys())
                if trade.entry_strategy_attributions
                else ([trade.winning_strategy] if trade.winning_strategy else ["UNKNOWN"])
            )
            exit_strats = (
                list(trade.exit_strategy_attributions.keys())
                if trade.exit_strategy_attributions
                else ([trade.exit_winning_strategy] if trade.exit_winning_strategy else ["UNKNOWN"])
            )
            for strat in entry_strats:
                entry_trades[strat].append(trade)
            for strat in exit_strats:
                exit_trades[strat].append(trade)

        return {
            "entry": {strat: cls.calculate_metrics(group) for strat, group in entry_trades.items()},
            "exit": {strat: cls.calculate_metrics(group) for strat, group in exit_trades.items()},
        }

    @classmethod
    def _calculate_proportional_metrics(  # pylint: disable=too-many-locals
            cls, weighted_trades: list[tuple[Trade, float]]
    ) -> AttributionMetrics:
        if not weighted_trades:
            return cls._empty_metrics()

        total = len(weighted_trades)
        wins = 0
        losses = 0
        break_even = 0
        gross_pnl = Decimal(0)
        fees = Decimal(0)
        slippage = Decimal(0)
        net_pnl = Decimal(0)
        gross_wins = Decimal(0)
        gross_losses = Decimal(0)
        max_win = Decimal(0)
        max_loss = Decimal(0)

        total_weight = sum(share for _, share in weighted_trades)
        weighted_wins = 0.0
        weighted_return = Decimal(0)
        weighted_duration = 0.0

        for trade, share in weighted_trades:
            share_dec = Decimal(str(share))
            prop_gross = trade.gross_pnl * share_dec
            prop_fees = trade.fees * share_dec
            prop_slippage = trade.slippage * share_dec
            prop_net = trade.net_pnl * share_dec

            gross_pnl += prop_gross
            fees += prop_fees
            slippage += prop_slippage
            net_pnl += prop_net

            if prop_net > Decimal(0):
                wins += 1
                weighted_wins += share
                gross_wins += prop_net
                max_win = max(max_win, prop_net)
            elif prop_net < Decimal(0):
                losses += 1
                gross_losses += abs(prop_net)
                max_loss = min(max_loss, prop_net)
            else:
                break_even += 1

            weighted_return += trade.return_pct * share_dec
            weighted_duration += trade.duration_seconds * share

        win_rate = round((weighted_wins / total_weight * 100.0) if total_weight > 0 else 0.0, 2)
        avg_ret = round(float(weighted_return / Decimal(str(total_weight))), 4) if total_weight > 0 else 0.0
        avg_dur = round(weighted_duration / total_weight, 2) if total_weight > 0 else 0.0

        if gross_losses > Decimal(0):
            profit_factor = round(float(gross_wins / gross_losses), 2)
        elif gross_wins > Decimal(0):
            profit_factor = 999.99
        else:
            profit_factor = 0.0

        return AttributionMetrics(
            total_trades=total,
            winning_trades=wins,
            losing_trades=losses,
            break_even_trades=break_even,
            win_rate_pct=win_rate,
            gross_pnl=gross_pnl,
            total_fees=fees,
            total_slippage=slippage,
            net_pnl=net_pnl,
            profit_factor=profit_factor,
            avg_return_pct=avg_ret,
            avg_duration_seconds=avg_dur,
            max_win=max_win,
            max_loss=max_loss,
        )

    @classmethod
    def attribute_by_symbol(cls, trades: list[Trade]) -> dict[str, AttributionMetrics]:
        grouped: dict[str, list[Trade]] = defaultdict(list)
        for trade in trades:
            grouped[trade.ticker_symbol].append(trade)
        return {symbol: cls.calculate_metrics(group) for symbol, group in grouped.items()}

    @classmethod
    def attribute_by_regime(cls, trades: list[Trade]) -> dict[str, AttributionMetrics]:
        grouped: dict[str, list[Trade]] = defaultdict(list)
        for trade in trades:
            regime = trade.entry_regime or trade.exit_regime or "UNKNOWN"
            grouped[regime].append(trade)
        return {regime: cls.calculate_metrics(group) for regime, group in grouped.items()}

    @classmethod
    def attribute_strategy_by_regime(
            cls, trades: list[Trade]
    ) -> dict[str, dict[str, AttributionMetrics]]:
        regime_grouped: dict[str, list[Trade]] = defaultdict(list)
        for trade in trades:
            regime = trade.entry_regime or trade.exit_regime or "UNKNOWN"
            regime_grouped[regime].append(trade)

        result: dict[str, dict[str, AttributionMetrics]] = defaultdict(dict)
        for regime, r_trades in regime_grouped.items():
            strat_metrics = cls.attribute_by_strategy_proportional(r_trades)
            for strat, metrics in strat_metrics.items():
                result[strat][regime] = metrics
        return dict(result)

    @classmethod
    def compute_co_voting_by_regime(
            cls, trades: list[Trade]
    ) -> dict[str, dict[str, Any]]:
        regime_grouped: dict[str, list[Trade]] = defaultdict(list)
        for trade in trades:
            regime = trade.entry_regime or trade.exit_regime or "UNKNOWN"
            regime_grouped[regime].append(trade)

        result: dict[str, dict[str, Any]] = {}
        all_matrix, all_counts = cls.compute_co_voting_details(trades)
        result["ALL"] = {"matrix": all_matrix, "counts": all_counts}

        for regime, r_trades in regime_grouped.items():
            matrix, counts = cls.compute_co_voting_details(r_trades)
            result[regime] = {"matrix": matrix, "counts": counts}
        return result

    @staticmethod
    def _empty_metrics() -> AttributionMetrics:
        return AttributionMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            break_even_trades=0,
            win_rate_pct=0.0,
            gross_pnl=Decimal(0),
            total_fees=Decimal(0),
            total_slippage=Decimal(0),
            net_pnl=Decimal(0),
            profit_factor=0.0,
            avg_return_pct=0.0,
            avg_duration_seconds=0.0,
            max_win=Decimal(0),
            max_loss=Decimal(0),
        )
