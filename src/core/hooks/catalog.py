from __future__ import annotations


class HookCatalog:
    """Canonical namespaced hook identifiers used across the application."""

    EXPERIMENT_RUN = "experiment.run"
    BACKTEST_RUN = "backtest.run"
    WALK_FORWARD_RUN = "walk_forward.run"
    DRIFT_CHECK = "drift.check"
    PROMOTION_EVALUATE = "promotion.evaluate"
