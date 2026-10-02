from __future__ import annotations

from decimal import Decimal
from typing import Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.helpers.format_helper import FormatHelper
from src.trading.protection.portfolio_risk_manager import PortfolioRiskManager


class PortfolioSummaryInput(BaseModel):
    quote_currency: Optional[str] = Field(
        default=None,
        description="Filter by specific quote currency (e.g. 'USD', 'USDC'). None for all portfolios.",
    )
    exchange: Optional[str] = Field(
        default=None,
        description="Filter by specific exchange (e.g. 'CRYPTO_DOT_COM', 'BINANCE'). None for all exchanges.",
    )


class PortfolioSummaryTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "portfolio_summary"
    description: str = (
        "Inspects multi-asset quote portfolios: mark-to-market total equity, cash balance, "
        "reserved order cash, current drawdown %, peak equity, and single-asset concentration levels."
    )
    args_schema: Type[BaseModel] = PortfolioSummaryInput
    portfolio_risk_manager: PortfolioRiskManager

    def __init__(self, portfolio_risk_manager: PortfolioRiskManager):
        super().__init__(portfolio_risk_manager=portfolio_risk_manager)

    def _run(  # pylint: disable=arguments-differ
            self,
            quote_currency: Optional[str] = None,
            exchange: Optional[str] = None,
    ) -> str:
        p_mgr = self.portfolio_risk_manager
        if not p_mgr.portfolios:
            return "No active quote portfolios registered in the portfolio risk manager."

        target_quote = quote_currency.strip().upper() if quote_currency else None
        target_exchange = exchange.strip().upper() if exchange else None

        matched_portfolios = []
        for (ex, quote), portfolio in p_mgr.portfolios.items():
            if target_exchange and ex.upper() != target_exchange:
                continue
            if target_quote and quote.upper() != target_quote:
                continue
            matched_portfolios.append(portfolio)

        if not matched_portfolios:
            return f"No portfolios matching exchange='{exchange}' and quote_currency='{quote_currency}'."

        sections = []
        for p in matched_portfolios:
            pos_lines = []
            for ticker, qty in p.asset_positions.items():
                price = p.asset_mark_prices.get(ticker, Decimal("0"))
                val = qty * price
                conc = p.get_asset_concentration(ticker) * Decimal("100")
                pos_lines.append(
                    f"    • {ticker}: {FormatHelper.format_decimal(qty)} units @ ${FormatHelper.format_decimal(price)} "
                    f"= ${FormatHelper.format_decimal(val)} {p.quote_currency} ({FormatHelper.format_decimal(conc)}% of portfolio)"
                )
            pos_text = "\n".join(pos_lines) if pos_lines else "    • (No open base asset positions)"

            dd_limit_str = f"{FormatHelper.format_decimal(p_mgr.max_portfolio_drawdown)}%" if p_mgr.max_portfolio_drawdown else "Not set"
            conc_limit_str = f"{FormatHelper.format_decimal(p_mgr.max_asset_concentration)}%" if p_mgr.max_asset_concentration else "Not set"
            current_dd_pct = abs(p.get_drawdown()) * Decimal("100")

            section = (
                f"Portfolio [{p.exchange} / {p.quote_currency}]:\n"
                f"  Total Mark-to-Market Equity: ${FormatHelper.format_decimal(p.get_total_equity())} {p.quote_currency}\n"
                f"  Available Cash:             ${FormatHelper.format_decimal(p.available_cash)} {p.quote_currency}\n"
                f"  Reserved Order Cash:        ${FormatHelper.format_decimal(p.reserved_cash)} {p.quote_currency}\n"
                f"  Total Cash Balance:         ${FormatHelper.format_decimal(p.total_cash)} {p.quote_currency}\n"
                f"  Peak Equity (HWM):          ${FormatHelper.format_decimal(p.peak_equity)} {p.quote_currency}\n"
                f"  Current Drawdown:           {FormatHelper.format_decimal(current_dd_pct)}% (Limit: {dd_limit_str})\n"
                f"  Max Concentration Limit:    {conc_limit_str}\n"
                f"  Positions Breakdown:\n{pos_text}"
            )
            sections.append(section)

        return "\n\n".join(sections)
