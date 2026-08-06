from __future__ import annotations

from typing import Optional

from mcp.server import MCPServer

from database.database_manager import DatabaseManager
from src.configuration.trading_config import TradingConfig
from src.core.expressions.expression_parser import ExpressionParser
from src.trading.consensus.consensus_factor import ConsensusFactor
from vcs.application.service import VCSService
from vcs.domain.exceptions import InvalidReferenceError


class TradingConfigMCPServer:
    _MCP_AUTHOR = "mcp-server"
    _MCP_NAME = "trading-config"
    _MCP_INSTRUCTIONS = (
        "Provides tools to inspect and update the trading bot's runtime configuration. "
        "Changes are committed to the versioned configuration store and picked up by "
        "the running application."
    )

    def __init__(self, vcs: Optional[VCSService] = None):
        self._vcs = vcs
        self._mcp = MCPServer(self._MCP_NAME, instructions=self._MCP_INSTRUCTIONS)
        self._mcp.add_tool(self.get_trading_config)
        self._mcp.add_tool(self.update_consensus)
        self._mcp.add_tool(self.update_dynamic_quantity)

    @property
    def mcp(self) -> MCPServer:
        return self._mcp

    def _get_config_vcs(self) -> VCSService:
        if self._vcs is None:
            db_manager = DatabaseManager()
            db_manager.initialize()
            self._vcs = VCSService(db_manager)
        return self._vcs

    def _checkout_head(self) -> TradingConfig:
        try:
            raw = self._get_config_vcs().checkout("HEAD")
            return TradingConfig.model_validate(raw)
        except InvalidReferenceError as exc:
            raise ValueError(
                "No configuration has been committed to the versioned config store yet. "
                "Commit an initial configuration before updating runtime settings."
            ) from exc

    # ---------------------------------------------------------------------------
    # Read tool
    # ---------------------------------------------------------------------------

    def get_trading_config(self) -> dict:
        """Return the current TradingConfig values from the versioned config store.

        Returns the complete config excluding assets, which are not modifiable at runtime.
        """
        config = self._checkout_head()
        return {
            "consensus": {
                "buy": config.consensus.buy,
                "sell": config.consensus.sell,
            },
            "dynamic_quantity": config.dynamic_quantity,
        }

    # ---------------------------------------------------------------------------
    # Consensus tools
    # ---------------------------------------------------------------------------

    def update_consensus(self, buy: float, sell: float) -> dict:
        """Update the consensus buy/sell thresholds.

        The consensus factor determines how strongly signals must agree before a
        trade is executed. A higher buy value requires stronger agreement to buy;
        a lower sell value requires weaker agreement to sell.

        Args:
            buy: The new buy threshold (e.g. 1.3). Must be > 0.
            sell: The new sell threshold (e.g. 0.5). Must be > 0 and <= buy.
        """
        if buy <= 0:
            raise ValueError(f"buy must be > 0, got {buy}")
        if sell <= 0:
            raise ValueError(f"sell must be > 0, got {sell}")
        if sell > buy:
            raise ValueError(f"sell ({sell}) must be <= buy ({buy})")

        config = self._checkout_head()
        config.consensus = ConsensusFactor(buy=buy, sell=sell)
        self._get_config_vcs().commit(
            config,
            author=self._MCP_AUTHOR,
            message=f"Update consensus to buy={buy}, sell={sell}",
        )

        return {"updated": {"consensus": {"buy": buy, "sell": sell}}}

    # ---------------------------------------------------------------------------
    # Dynamic quantity tools
    # ---------------------------------------------------------------------------

    def update_dynamic_quantity(self, formula: str) -> dict:
        """Update the dynamic quantity formula.

        The formula is a Python expression evaluated at order time. Available
        variables: min_qty, equity, risk_pct, close, signal, pnl, and any
        indicator function like rsi(period).

        Args:
            formula: The new formula string. Pass an empty string to disable
                     dynamic quantity (falls back to min_quantity per asset).
        """
        ExpressionParser.validate(formula)

        config = self._checkout_head()
        config.dynamic_quantity = formula if formula else None
        self._get_config_vcs().commit(
            config,
            author=self._MCP_AUTHOR,
            message="Update dynamic quantity formula",
        )

        return {"updated": {"dynamic_quantity": formula or None}}


mcp = TradingConfigMCPServer().mcp
