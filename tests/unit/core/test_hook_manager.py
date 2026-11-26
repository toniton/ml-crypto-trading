from __future__ import annotations

import threading

import pytest

from src.core.hooks import (
    HookCatalog,
    HookContext,
    HookExecutionMode,
    HookManager,
    HookStage,
)


@pytest.fixture
def hook_manager():
    manager = HookManager(max_workers=2)
    yield manager
    manager.close(wait=True)


def test_register_and_emit_respects_priority_and_stages(hook_manager: HookManager):
    order: list[str] = []

    hook_manager.register(
        HookCatalog.EXPERIMENT_RUN,
        lambda _ctx: order.append("second"),
        stages=(HookStage.COMPLETED,),
        priority=200,
    )
    hook_manager.register(
        HookCatalog.EXPERIMENT_RUN,
        lambda _ctx: order.append("first"),
        stages=(HookStage.COMPLETED,),
        priority=10,
    )
    hook_manager.register(
        HookCatalog.EXPERIMENT_RUN,
        lambda _ctx: order.append("started_only"),
        stages=(HookStage.STARTED,),
        priority=1,
    )

    result = hook_manager.emit(
        HookContext(
            hook_name=HookCatalog.EXPERIMENT_RUN,
            stage=HookStage.COMPLETED,
            source_id="exp_1",
        )
    )

    assert order == ["first", "second"]
    assert result.matched_count == 2
    assert result.sync_executed == 2
    assert result.failures == ()


def test_wildcard_matching_and_predicate_filtering(hook_manager: HookManager):
    seen: list[str] = []

    hook_manager.register(
        "experiment.*",
        lambda ctx: seen.append(f"{ctx.hook_name}:{ctx.source_id}"),
        stages=(HookStage.COMPLETED,),
        predicate=lambda ctx: ctx.payload.get("ticker_symbol") == "BTC_USD",
    )

    hook_manager.emit(
        HookContext(
            hook_name="experiment.run",
            stage=HookStage.COMPLETED,
            source_id="exp_eth",
            payload={"ticker_symbol": "ETH_USD"},
        )
    )
    hook_manager.emit(
        HookContext(
            hook_name="experiment.run",
            stage=HookStage.COMPLETED,
            source_id="exp_btc",
            payload={"ticker_symbol": "BTC_USD"},
        )
    )

    assert seen == ["experiment.run:exp_btc"]


def test_register_once_auto_unregisters_after_first_match(hook_manager: HookManager):
    calls: list[str] = []

    hook_manager.register_once(
        HookCatalog.EXPERIMENT_RUN,
        lambda ctx: calls.append(ctx.source_id),
        source_id="exp_target",
        stages=(HookStage.COMPLETED,),
    )

    hook_manager.emit(
        HookContext(
            hook_name=HookCatalog.EXPERIMENT_RUN,
            stage=HookStage.COMPLETED,
            source_id="exp_other",
        )
    )
    assert calls == []
    assert hook_manager.listener_count(HookCatalog.EXPERIMENT_RUN) == 1

    hook_manager.emit(
        HookContext(
            hook_name=HookCatalog.EXPERIMENT_RUN,
            stage=HookStage.COMPLETED,
            source_id="exp_target",
        )
    )
    hook_manager.emit(
        HookContext(
            hook_name=HookCatalog.EXPERIMENT_RUN,
            stage=HookStage.COMPLETED,
            source_id="exp_target",
        )
    )

    assert calls == ["exp_target"]
    assert hook_manager.listener_count(HookCatalog.EXPERIMENT_RUN) == 0


def test_sync_handler_exception_is_isolated(hook_manager: HookManager):
    reached: list[str] = []

    def failing_handler(_ctx: HookContext) -> None:
        raise RuntimeError("boom")

    hook_manager.register(
        "job.run",
        failing_handler,
        stages=(HookStage.COMPLETED,),
        priority=10,
        name="failing",
    )
    hook_manager.register(
        "job.run",
        lambda _ctx: reached.append("ok"),
        stages=(HookStage.COMPLETED,),
        priority=20,
        name="healthy",
    )

    result = hook_manager.emit(
        HookContext(hook_name="job.run", stage=HookStage.COMPLETED, source_id="j1")
    )

    assert reached == ["ok"]
    assert len(result.failures) == 1
    assert result.failures[0].handler_name == "failing"
    assert "boom" in result.failures[0].error


def test_async_mode_executes_listener_on_worker_thread(hook_manager: HookManager):
    done = threading.Event()
    received: list[str] = []

    def async_handler(ctx: HookContext) -> None:
        received.append(ctx.source_id)
        done.set()

    hook_manager.register(
        HookCatalog.EXPERIMENT_RUN,
        async_handler,
        stages=(HookStage.COMPLETED,),
        mode=HookExecutionMode.ASYNC,
    )

    result = hook_manager.emit(
        HookContext(
            hook_name=HookCatalog.EXPERIMENT_RUN,
            stage=HookStage.COMPLETED,
            source_id="exp_async",
        )
    )

    assert result.async_submitted == 1
    assert done.wait(timeout=3.0)
    assert received == ["exp_async"]


def test_track_context_manager_emits_lifecycle_stages(hook_manager: HookManager):
    events: list[tuple[HookStage, str | None]] = []

    hook_manager.register(
        "pipeline.step",
        lambda ctx: events.append((ctx.stage, ctx.state)),
        stages=(
            HookStage.STARTED,
            HookStage.STATE_CHANGED,
            HookStage.COMPLETED,
            HookStage.FINALLY,
        ),
    )

    with hook_manager.track("pipeline.step", source_id="s1") as tracker:
        tracker.transition("AGGREGATING")

    assert events == [
        (HookStage.STARTED, "STARTED"),
        (HookStage.STATE_CHANGED, "AGGREGATING"),
        (HookStage.COMPLETED, "COMPLETED"),
        (HookStage.FINALLY, "COMPLETED"),
    ]


def test_track_emits_failed_and_finally_on_exception(hook_manager: HookManager):
    stages: list[tuple[HookStage, str | None]] = []
    hook_manager.register(
        "pipeline.fail",
        lambda ctx: stages.append((ctx.stage, ctx.error)),
        stages=(HookStage.STARTED, HookStage.FAILED, HookStage.FINALLY),
    )

    with pytest.raises(ValueError, match="bad input"):
        with hook_manager.track("pipeline.fail", source_id="f1"):
            raise ValueError("bad input")

    assert stages == [
        (HookStage.STARTED, None),
        (HookStage.FAILED, "bad input"),
        (HookStage.FINALLY, "bad input"),
    ]


def test_wrap_instruments_callable(hook_manager: HookManager):
    observed: list[tuple[HookStage, object]] = []
    hook_manager.register(
        "math.double",
        lambda ctx: observed.append((ctx.stage, ctx.payload.get("result"))),
        stages=(HookStage.STARTED, HookStage.COMPLETED),
    )

    wrapped = hook_manager.wrap(
        "math.double",
        lambda x: x * 2,
        source_id_factory=lambda x: f"val_{x}",
    )

    assert wrapped(21) == 42
    assert observed == [(HookStage.STARTED, None), (HookStage.COMPLETED, 42)]


def test_when_all_fires_once_all_targets_complete(hook_manager: HookManager):
    combined: list[list[str]] = []

    hook_manager.when_all(
        [
            (HookCatalog.EXPERIMENT_RUN, "exp_1"),
            (HookCatalog.DRIFT_CHECK, "drift_1"),
        ],
        lambda contexts: combined.append([c.source_id for c in contexts]),
    )

    hook_manager.emit(
        HookContext(
            hook_name=HookCatalog.EXPERIMENT_RUN,
            stage=HookStage.COMPLETED,
            source_id="exp_1",
        )
    )
    assert combined == []

    hook_manager.emit(
        HookContext(
            hook_name=HookCatalog.DRIFT_CHECK,
            stage=HookStage.COMPLETED,
            source_id="drift_1",
        )
    )
    assert combined == [["exp_1", "drift_1"]]
