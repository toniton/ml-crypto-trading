from __future__ import annotations

import abc
from typing import List

from api.interfaces.asset import Asset
from src.trading.reconciliation.models.discrepancy import Discrepancy


class BaseReconciler(abc.ABC):
    @abc.abstractmethod
    def reconcile(self, exchange: str, assets: List[Asset]) -> List[Discrepancy]:
        raise NotImplementedError()
