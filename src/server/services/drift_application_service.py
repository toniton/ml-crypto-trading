from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import inspect
import threading
from typing import Any, Callable, Optional

from api.interfaces.drift import (
    DriftAttributionFactor,
    DriftEquityPoint,
    DriftSnapshotResponse,
)
from src.backtest.analysis.drift_detector import DriftReport
from src.server.services.asset_performance_service import AssetPerformanceService
from src.vcs.application.service import VCSService

PRICE_DRIFT_WARN_THRESHOLD_PCT = 0.25
PRICE_DRIFT_ALERT_THRESHOLD_PCT = 0.5
FEE_DRIFT_WARN_THRESHOLD = 0.01
DEFAULT_LIVE_WINDOW_DAYS = 30


def extract_quote_currency(symbol: str) -> str:
    for separator in ("_", "-", "/"):
        if separator in symbol:
            parts = symbol.split(separator)
            if len(parts) >= 2 and parts[-1]:
                return parts[-1].upper()
    return "USD"


def _parse_iso_epoch(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return None


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return None


class DriftApplicationService:
    def __init__(
            self,
            detect_fn: Optional[Callable[..., DriftReport]] = None,
            vcs_service: Optional[VCSService] = None,
            asset_performance_service: Optional[AssetPerformanceService] = None,
            venue: str = "default",
    ) -> None:
        self._detect_fn = detect_fn
        self._vcs_service = vcs_service
        self._asset_performance_service = asset_performance_service
        self._venue = venue
        self._lock = threading.Lock()
        self._snapshots: dict[tuple[str, str], DriftSnapshotResponse] = {}

    def get_snapshot(
            self,
            symbol: str,
            commit_hash: Optional[str] = None,
    ) -> Optional[DriftSnapshotResponse]:
        with self._lock:
            if commit_hash:
                target = commit_hash.strip()
                if (symbol, target) in self._snapshots:
                    return self._snapshots[(symbol, target)]
                for (cached_symbol, cached_commit), snapshot in reversed(list(self._snapshots.items())):
                    if cached_symbol == symbol and cached_commit and (
                        cached_commit == target
                        or (len(target) >= 7 and cached_commit.startswith(target))
                        or (len(cached_commit) >= 7 and target.startswith(cached_commit))
                    ):
                        return snapshot
                return None

            resolved_commit = self._resolve_head_commit()
            if resolved_commit and (symbol, resolved_commit) in self._snapshots:
                return self._snapshots[(symbol, resolved_commit)]
            for (cached_symbol, _), snapshot in reversed(list(self._snapshots.items())):
                if cached_symbol == symbol:
                    return snapshot
        return None

    def run_drift_check(
            self,
            symbol: str,
            commit_hash: Optional[str] = None,
    ) -> DriftSnapshotResponse:
        if self._detect_fn is None:
            raise RuntimeError("Drift detection is not enabled on this engine instance.")

        resolved_commit = commit_hash or self._resolve_head_commit()
        report = self._invoke_detect(symbol, commit_hash)
        snapshot = self._build_snapshot(symbol, report, resolved_commit)

        cache_key = (symbol, resolved_commit or "HEAD")
        with self._lock:
            self._snapshots[cache_key] = snapshot
        return snapshot

    def _invoke_detect(self, symbol: str, commit_hash: Optional[str]) -> DriftReport:
        if self._detect_fn is None:
            raise RuntimeError("Drift detection is not enabled on this engine instance.")
        try:
            params = inspect.signature(self._detect_fn).parameters
            accepts_commit = "commit_hash" in params or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
            )
        except (TypeError, ValueError):
            accepts_commit = False

        if accepts_commit:
            return self._detect_fn(symbol, commit_hash=commit_hash)
        return self._detect_fn(symbol)

    def _resolve_head_commit(self) -> Optional[str]:
        if self._vcs_service is None:
            return None
        try:
            head = self._vcs_service.resolve_ref("HEAD")
            return head if isinstance(head, str) else None
        except Exception:  # pylint: disable=broad-except
            return None

    def _build_snapshot(
            self,
            symbol: str,
            report: DriftReport,
            commit_hash: Optional[str],
    ) -> DriftSnapshotResponse:
        quote_currency = extract_quote_currency(symbol)
        sim_price = _to_float(report.simulated_average_price)
        live_price = _to_float(report.live_average_price)
        price_drift = _to_float(report.price_drift)
        sim_fees = _to_float(report.simulated_fees) or 0.0
        live_fees = _to_float(report.live_fees) or 0.0
        fee_drift = _to_float(report.fee_drift) or 0.0
        sim_qty = _to_float(report.simulated_quantity) or 0.0
        live_qty = _to_float(report.live_quantity) or 0.0
        qty_drift = _to_float(report.quantity_drift) or 0.0

        simulated_curve = tuple(getattr(report, "simulated_equity_curve", ()) or ())
        if simulated_curve:
            live_pnl, equity_series = self._build_aligned_equity_series(
                symbol=symbol,
                simulated_curve=simulated_curve,
                window_start=report.window_start,
                window_end=report.window_end,
            )
            report_sim_pnl = _to_float(getattr(report, "simulated_pnl", None))
            simulated_pnl = (
                round(report_sim_pnl, 4)
                if report_sim_pnl is not None
                else round(simulated_curve[-1][1], 4)
            )
            if live_pnl is None:
                live_pnl = 0.0
        else:
            live_pnl, equity_series = self._build_live_equity_series(
                symbol=symbol,
                fee_drift=fee_drift,
                price_drift=price_drift,
                live_qty=live_qty,
            )
            simulated_pnl = (
                round(live_pnl + self._estimate_pnl_gap(fee_drift, price_drift, live_qty), 4)
                if live_pnl is not None
                else None
            )
        pnl_gap = (
            round(simulated_pnl - live_pnl, 4)
            if simulated_pnl is not None and live_pnl is not None
            else None
        )

        factors = self._build_attribution_factors(
            quote_currency=quote_currency,
            sim_fees=sim_fees,
            live_fees=live_fees,
            fee_drift=fee_drift,
            sim_price=sim_price,
            live_price=live_price,
            price_drift=price_drift,
            sim_fills=report.simulated_fill_count,
            live_fills=report.live_fill_count,
            fill_count_drift=report.fill_count_drift,
            sim_qty=sim_qty,
            live_qty=live_qty,
            qty_drift=qty_drift,
            simulated_pnl=simulated_pnl,
            live_pnl=live_pnl,
            pnl_gap=pnl_gap,
        )

        return DriftSnapshotResponse(
            symbol=symbol,
            venue=self._venue,
            quote_currency=quote_currency,
            commit_hash=commit_hash,
            computed_at=datetime.now(timezone.utc).isoformat(),
            window_start=report.window_start,
            window_end=report.window_end,
            drifted=report.drifted,
            simulated_fill_count=report.simulated_fill_count,
            live_fill_count=report.live_fill_count,
            fill_count_drift=report.fill_count_drift,
            simulated_quantity=sim_qty,
            live_quantity=live_qty,
            quantity_drift=qty_drift,
            simulated_average_price=sim_price,
            live_average_price=live_price,
            price_drift=price_drift,
            simulated_fees=sim_fees,
            live_fees=live_fees,
            fee_drift=fee_drift,
            simulated_pnl=simulated_pnl,
            live_pnl=live_pnl,
            pnl_gap=pnl_gap,
            partial_fill_legs_merged=report.partial_fill_legs_merged,
            attribution_factors=factors,
            equity_series=equity_series,
        )

    def _build_aligned_equity_series(
            self,
            symbol: str,
            simulated_curve: tuple[tuple[str, float], ...],
            window_start: Optional[str],
            window_end: Optional[str],
    ) -> tuple[Optional[float], list[DriftEquityPoint]]:
        live_pnl, live_points = self._load_live_curve_points(symbol, window_start, window_end)

        live_idx = 0
        current_live_cum = 0.0
        series: list[DriftEquityPoint] = []

        for iso_ts, sim_cum in simulated_curve:
            sim_epoch = _parse_iso_epoch(iso_ts)
            if sim_epoch is not None:
                while live_idx < len(live_points) and live_points[live_idx][0] <= sim_epoch:
                    current_live_cum = live_points[live_idx][1]
                    live_idx += 1

            sim_val = round(float(sim_cum), 4)
            live_val = round(current_live_cum, 4)
            series.append(
                DriftEquityPoint(
                    timestamp=iso_ts,
                    simulated_cumulative_pnl=sim_val,
                    live_cumulative_pnl=live_val,
                    gap=round(sim_val - live_val, 4),
                )
            )

        return live_pnl, series

    def _load_live_curve_points(
            self,
            symbol: str,
            window_start: Optional[str],
            window_end: Optional[str],
    ) -> tuple[Optional[float], list[tuple[float, float]]]:
        if self._asset_performance_service is None:
            return None, []

        now = datetime.now(timezone.utc)
        start_dt = _parse_iso_datetime(window_start) or (now - timedelta(days=DEFAULT_LIVE_WINDOW_DAYS))
        end_dt = _parse_iso_datetime(window_end) or now
        if end_dt < start_dt:
            end_dt = now

        try:
            perf = self._asset_performance_service.calculate_performance(
                ticker_symbol=symbol,
                start=start_dt,
                end=end_dt,
            )
        except Exception:  # pylint: disable=broad-except
            return None, []

        live_pnl = _to_float(perf.summary.realized_pnl) if perf.summary else None
        raw_curve = perf.equity_curve or []
        points: list[tuple[float, float]] = []
        for pt in raw_curve:
            epoch = _parse_iso_epoch(pt.timestamp)
            if epoch is not None:
                points.append((epoch, _to_float(pt.cumulative_pnl) or 0.0))
        points.sort(key=lambda item: item[0])
        return live_pnl, points

    def _build_live_equity_series(
            self,
            symbol: str,
            fee_drift: float,
            price_drift: Optional[float],
            live_qty: float,
    ) -> tuple[Optional[float], list[DriftEquityPoint]]:
        if self._asset_performance_service is None:
            return None, []
        try:
            now = datetime.now(timezone.utc)
            perf = self._asset_performance_service.calculate_performance(
                ticker_symbol=symbol,
                start=now - timedelta(days=DEFAULT_LIVE_WINDOW_DAYS),
                end=now,
            )
        except Exception:  # pylint: disable=broad-except
            return None, []

        live_pnl = _to_float(perf.summary.realized_pnl) if perf.summary else None
        raw_curve = perf.equity_curve or []
        if not raw_curve:
            return live_pnl, []

        total_gap = self._estimate_pnl_gap(fee_drift, price_drift, live_qty)
        point_count = len(raw_curve)
        series: list[DriftEquityPoint] = []
        for idx, pt in enumerate(raw_curve):
            live_cum = _to_float(pt.cumulative_pnl) or 0.0
            progress = (idx + 1) / point_count
            sim_cum = round(live_cum + total_gap * progress, 4)
            series.append(
                DriftEquityPoint(
                    timestamp=pt.timestamp,
                    simulated_cumulative_pnl=sim_cum,
                    live_cumulative_pnl=round(live_cum, 4),
                    gap=round(sim_cum - live_cum, 4),
                )
            )
        return live_pnl, series

    @staticmethod
    def _estimate_pnl_gap(
            fee_drift: float,
            price_drift: Optional[float],
            live_qty: float,
    ) -> float:
        slippage_impact = abs(price_drift or 0.0) * live_qty
        return round(abs(fee_drift) + slippage_impact, 4)

    @staticmethod
    def _build_attribution_factors(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            quote_currency: str,
            sim_fees: float,
            live_fees: float,
            fee_drift: float,
            sim_price: Optional[float],
            live_price: Optional[float],
            price_drift: Optional[float],
            sim_fills: int,
            live_fills: int,
            fill_count_drift: int,
            sim_qty: float,
            live_qty: float,
            qty_drift: float,
            simulated_pnl: Optional[float],
            live_pnl: Optional[float],
            pnl_gap: Optional[float],
    ) -> list[DriftAttributionFactor]:
        price_severity = "ok"
        if price_drift is not None and live_price:
            pct = abs(price_drift) / live_price * 100.0
            if pct > PRICE_DRIFT_ALERT_THRESHOLD_PCT:
                price_severity = "drift"
            elif pct > PRICE_DRIFT_WARN_THRESHOLD_PCT:
                price_severity = "warn"

        fee_severity = "warn" if abs(fee_drift) > FEE_DRIFT_WARN_THRESHOLD else "ok"
        fill_severity = "drift" if fill_count_drift != 0 else "ok"
        qty_severity = "drift" if abs(qty_drift) > 0 else "ok"

        factors = [
            DriftAttributionFactor(
                category="price_slippage",
                label="Average Fill Price",
                simulated_value=sim_price,
                live_value=live_price,
                delta=price_drift,
                unit=quote_currency,
                severity=price_severity,
            ),
            DriftAttributionFactor(
                category="fees",
                label="Execution Fees",
                simulated_value=sim_fees,
                live_value=live_fees,
                delta=fee_drift,
                unit=quote_currency,
                severity=fee_severity,
            ),
            DriftAttributionFactor(
                category="fill_count",
                label="Fill Count",
                simulated_value=float(sim_fills),
                live_value=float(live_fills),
                delta=float(fill_count_drift),
                unit="fills",
                severity=fill_severity,
            ),
            DriftAttributionFactor(
                category="quantity",
                label="Executed Quantity",
                simulated_value=sim_qty,
                live_value=live_qty,
                delta=qty_drift,
                unit="units",
                severity=qty_severity,
            ),
        ]
        if simulated_pnl is not None and live_pnl is not None:
            factors.append(
                DriftAttributionFactor(
                    category="pnl",
                    label="Realized PnL Gap",
                    simulated_value=simulated_pnl,
                    live_value=live_pnl,
                    delta=pnl_gap,
                    unit=quote_currency,
                    severity="warn" if (pnl_gap and abs(pnl_gap) > 0) else "ok",
                )
            )
        return factors
