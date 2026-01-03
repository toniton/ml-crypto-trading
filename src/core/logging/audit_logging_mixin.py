from __future__ import annotations
import logging
from datetime import datetime, UTC
from typing import Optional

from api.interfaces.market_data import MarketData
from src.core.logging.factory import LoggingFactory


class AuditLoggingMixin:
    @property
    def audit_logger(self) -> logging.Logger:
        return LoggingFactory.get_audit_logger()

    def log_audit_event(
            self,
            event_type: str,
            asset: str,
            action: str,
            market_data: Optional[MarketData] = None,
            context: str = ''
    ):
        timestamp = int(datetime.now(UTC).timestamp() * 1000)
        extra = {
            'timestamp': timestamp,
            'asset': asset,
            'event_type': event_type,
            'action': action,
            'close_price': market_data.close_price if market_data else '',
            'high_price': market_data.high_price if market_data else '',
            'low_price': market_data.low_price if market_data else '',
            'volume': market_data.volume if market_data else '',
            'context': context
        }

        logger = LoggingFactory.get_audit_logger(asset)
        logger.info(context, extra=extra)
