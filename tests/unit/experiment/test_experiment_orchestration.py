from __future__ import annotations
# pylint: disable=duplicate-code

from unittest.mock import MagicMock, patch

from api.interfaces.experiment import (
    CandidateType,
    ExperimentCandidate,
    ExperimentSpec,
    ExperimentStatus,
    TestSelection,
)
from src.server.services.experiment_application_service import (
    ExperimentApplicationService,
)


class TestExperimentOrchestration:  # pylint: disable=attribute-defined-outside-init,protected-access
    def setup_method(self):
        self.mock_db = MagicMock()
        self.mock_uow = MagicMock()
        self.mock_db.get_unit_of_work.return_value.__enter__.return_value = self.mock_uow
        self.mock_repo = MagicMock()
        self.mock_uow.get_repository.return_value = self.mock_repo

        self.mock_vcs = MagicMock()
        self.mock_vcs.resolve_commit_hash.return_value = "commit_sha_base_001"

        self.mock_backtest_service = MagicMock()
        self.mock_bt_app = MagicMock()
        self.mock_wf_app = MagicMock()

        self.service = ExperimentApplicationService(
            db_manager=self.mock_db,
            vcs_service=self.mock_vcs,
            backtest_service=self.mock_backtest_service,
            backtest_app_service=self.mock_bt_app,
            walk_forward_app_service=self.mock_wf_app,
        )

    def test_start_experiment_dispatches_backtest_only(self):
        spec = ExperimentSpec(
            name="BTC Backtest Only",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-btc-branch",
            test_selection=TestSelection.BACKTEST_ONLY,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current Configuration",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                )
            ],
        )
        self.mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_bt_01",
            "status": "DRAFT",
            "spec": spec.model_dump(mode="json"),
            "run_bindings": [],
        }

        mock_bt_session = MagicMock()
        mock_bt_session.id = "bt_sess_101"
        self.mock_bt_app.start_backtest_run.return_value = mock_bt_session

        with patch("threading.Thread") as mock_thread:
            self.service.start_experiment("exp_bt_01")
            mock_thread.assert_called_once()

        self.mock_bt_app.start_backtest_run.assert_called_once()
        self.mock_wf_app.start_run.assert_not_called()

        saved_bindings = self.mock_repo.save_experiment.call_args[1]["run_bindings"]
        assert len(saved_bindings) == 1
        assert saved_bindings[0]["backtest_session_id"] == "bt_sess_101"
        assert saved_bindings[0]["walk_forward_run_id"] is None
        assert saved_bindings[0]["status"] == "RUNNING"

    def test_start_experiment_dispatches_walk_forward_only(self):
        spec = ExperimentSpec(
            name="BTC Walk Forward Only",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-btc-branch",
            test_selection=TestSelection.WALK_FORWARD_ONLY,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current Configuration",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                )
            ],
        )
        self.mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_wf_01",
            "status": "DRAFT",
            "spec": spec.model_dump(mode="json"),
            "run_bindings": [],
        }

        self.mock_wf_app.start_run.return_value = {"run_id": "wf_run_202"}

        with patch("threading.Thread"):
            self.service.start_experiment("exp_wf_01")

        self.mock_bt_app.start_backtest_run.assert_not_called()
        self.mock_wf_app.start_run.assert_called_once()

        saved_bindings = self.mock_repo.save_experiment.call_args[1]["run_bindings"]
        assert len(saved_bindings) == 1
        assert saved_bindings[0]["backtest_session_id"] is None
        assert saved_bindings[0]["walk_forward_run_id"] == "wf_run_202"
        assert saved_bindings[0]["status"] == "RUNNING"

    def test_start_experiment_dispatches_both(self):
        spec = ExperimentSpec(
            name="BTC Dual Mode",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-btc-branch",
            test_selection=TestSelection.BOTH,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current Configuration",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                ),
                ExperimentCandidate(
                    candidate_id="cand_weights",
                    name="Proposed Weights",
                    candidate_type=CandidateType.PROPOSED_WEIGHTS,
                    strategy_weights={"TrendFollower": 1.5},
                ),
            ],
        )
        self.mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_both_01",
            "status": "DRAFT",
            "spec": spec.model_dump(mode="json"),
            "run_bindings": [],
        }

        mock_bt_session = MagicMock()
        mock_bt_session.id = "bt_sess_303"
        self.mock_bt_app.start_backtest_run.return_value = mock_bt_session
        self.mock_wf_app.start_run.return_value = {"run_id": "wf_run_404"}

        with patch("threading.Thread"):
            self.service.start_experiment("exp_both_01")

        assert self.mock_bt_app.start_backtest_run.call_count == 2
        assert self.mock_wf_app.start_run.call_count == 2

        saved_bindings = self.mock_repo.save_experiment.call_args[1]["run_bindings"]
        assert len(saved_bindings) == 2
        assert saved_bindings[0]["backtest_session_id"] == "bt_sess_303"
        assert saved_bindings[0]["walk_forward_run_id"] == "wf_run_404"

    def test_cancel_experiment(self):
        self.mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_cancel_01",
            "status": "RUNNING",
            "run_bindings": [
                {"candidate_id": "c1", "status": "RUNNING"},
                {"candidate_id": "c2", "status": "COMPLETED"},
            ],
        }

        success = self.service.cancel_experiment("exp_cancel_01")
        assert success is True
        self.mock_repo.update_status.assert_called_once_with("exp_cancel_01", ExperimentStatus.CANCELLED.value)

        updated_bindings = self.mock_repo.update_bindings.call_args[0][1]
        assert updated_bindings[0]["status"] == "CANCELLED"
        assert updated_bindings[1]["status"] == "COMPLETED"

    def test_retry_candidate(self):
        spec = ExperimentSpec(
            name="Retry Test",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-btc-branch",
            test_selection=TestSelection.BACKTEST_ONLY,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_failed",
                    name="Failed Candidate",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                )
            ],
        )
        self.mock_repo.get_experiment.return_value = {
            "experiment_id": "exp_retry_01",
            "status": "RUNNING",
            "spec": spec.model_dump(mode="json"),
            "run_bindings": [
                {
                    "candidate_id": "cand_failed",
                    "backtest_session_id": "old_bt_1",
                    "status": "FAILED",
                    "error": "Timeout error",
                }
            ],
        }

        mock_new_session = MagicMock()
        mock_new_session.id = "bt_retry_session_999"
        self.mock_bt_app.start_backtest_run.return_value = mock_new_session

        with patch("threading.Thread"):
            self.service.retry_candidate("exp_retry_01", "cand_failed")

        updated_bindings = self.mock_repo.update_bindings.call_args[0][1]
        assert len(updated_bindings) == 1
        assert updated_bindings[0]["candidate_id"] == "cand_failed"
        assert updated_bindings[0]["backtest_session_id"] == "bt_retry_session_999"
        assert updated_bindings[0]["status"] == "RUNNING"

    def test_compute_experiment_report_deltas(self):
        spec = ExperimentSpec(
            name="Report Aggregation Test",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-btc-branch",
            test_selection=TestSelection.BOTH,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current Config",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                ),
                ExperimentCandidate(
                    candidate_id="cand_custom",
                    name="Custom Weights",
                    candidate_type=CandidateType.PROPOSED_WEIGHTS,
                ),
            ],
        )
        bindings = [
            {
                "candidate_id": "cand_current",
                "backtest_session_id": "bt_1",
                "walk_forward_run_id": "wf_1",
                "status": "COMPLETED",
            },
            {
                "candidate_id": "cand_custom",
                "backtest_session_id": "bt_2",
                "walk_forward_run_id": "wf_2",
                "status": "COMPLETED",
            },
        ]

        mock_uow = MagicMock()
        mock_bt_repo = MagicMock()
        mock_wf_repo = MagicMock()

        def _get_repo(repo_type):
            name = repo_type.__name__
            if "Backtest" in name:
                return mock_bt_repo
            return mock_wf_repo

        mock_uow.get_repository.side_effect = _get_repo

        mock_bt_repo.get_result_metrics.side_effect = lambda sid: (
            {"percentage_return": 10.0, "max_drawdown_pct": 5.0}
            if sid == "bt_1"
            else {"percentage_return": 15.0, "max_drawdown_pct": 4.0}
        )
        mock_wf_repo.get_run.side_effect = lambda rid: (
            {"summary": {"aggregate_oos_return_pct": 8.0, "verdict": "ROBUST"}}
            if rid == "wf_1"
            else {"summary": {"aggregate_oos_return_pct": 14.0, "verdict": "ROBUST"}}
        )

        report = ExperimentApplicationService._compute_experiment_report(mock_uow, spec, bindings)

        assert report["summary"]["total_candidates"] == 2
        assert report["summary"]["completed_candidates"] == 2
        assert report["summary"]["failed_candidates"] == 0

        current_entry = report["candidates"]["cand_current"]
        custom_entry = report["candidates"]["cand_custom"]

        assert current_entry["backtest"]["percentage_return"] == 10.0
        assert custom_entry["backtest"]["percentage_return"] == 15.0
        # Delta: 15.0 - 10.0 = 5.0
        assert custom_entry["deltas"]["backtest_return_diff"] == 5.0
        # Walk forward delta: 14.0 - 8.0 = 6.0
        assert custom_entry["deltas"]["walk_forward_oos_return_diff"] == 6.0

    def test_resolve_candidate_commit_random_control(self):
        from api.interfaces.asset import Asset
        from api.interfaces.asset_schedule import AssetSchedule
        from api.interfaces.timeframe import Timeframe
        from api.interfaces.trade_action import TradeAction
        from src.configuration.strategy_config import StrategyConfig, StrategyType
        from src.configuration.trading_config import TradingConfig
        from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
        from src.trading.consensus.consensus_factor import ConsensusFactor

        self.mock_vcs.resolve_commit_hash.return_value = "commit_head_ref_001"
        base_config = TradingConfig(
            assets=[
                Asset(
                    base_ticker_symbol="BTC",
                    quote_ticker_symbol="USD",
                    quote_decimals=2,
                    name="Bitcoin",
                    exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
                    min_quantity=0.001,
                    quantity_decimals=5,
                    schedule=AssetSchedule.EVERY_MINUTE,
                    candles_timeframe=Timeframe.MIN1,
                    consensus=ConsensusFactor(buy=0.7, sell=0.4),
                    strategies=[
                        StrategyConfig(
                            name="TrendFollower",
                            type=StrategyType.DYNAMIC,
                            action=TradeAction.BUY,
                            expression="close > sma(20)",
                            enabled=True,
                            weight=2.0,
                        ),
                        StrategyConfig(
                            name="MeanReversion",
                            type=StrategyType.DYNAMIC,
                            action=TradeAction.BUY,
                            expression="rsi(14) < 30",
                            enabled=True,
                            weight=1.5,
                        ),
                    ],
                )
            ]
        )
        self.mock_vcs.checkout.return_value = base_config.model_dump(mode="json")

        mock_commit = MagicMock()
        mock_commit.hash = "commit_random_hash_999"
        self.mock_vcs.commit.return_value = mock_commit

        cand = ExperimentCandidate(
            candidate_id="cand_random_42",
            name="Random Control (42)",
            candidate_type=CandidateType.RANDOM_CONTROL,
            random_seed=42,
        )
        resolved_hash = self.service._resolve_candidate_commit("exp-branch-1", "BTC_USD", cand)

        assert resolved_hash == "commit_random_hash_999"
        assert cand.strategy_weights is not None
        assert "TrendFollower" in cand.strategy_weights
        assert "MeanReversion" in cand.strategy_weights
        self.mock_vcs.branch.assert_called_once_with(
            "refs/experiments/exp-branch-1/cand_random_42",
            from_ref="commit_head_ref_001",
        )
        self.mock_vcs.commit.assert_called_once()
        committed_cfg = self.mock_vcs.commit.call_args.kwargs["content"]
        assert isinstance(committed_cfg, TradingConfig)
        committed_weights = {s.name: s.weight for s in committed_cfg.assets[0].strategies}
        assert committed_weights == cand.strategy_weights

    def test_compute_experiment_report_harmonizes_all_candidate_strategies(self):
        spec = ExperimentSpec(
            name="Matrix Harmonization Test",
            ticker_symbol="BTC_USD",
            base_commit_hash="commit_sha_base_001",
            branch_id="exp-btc-branch",
            test_selection=TestSelection.BACKTEST_ONLY,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current Config",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                    strategy_weights={"BuyStrat1": 1.0, "SellStrat2": 1.5, "IdleStrat3": 0.5},
                ),
            ],
        )
        bindings = [
            {
                "candidate_id": "cand_current",
                "backtest_session_id": "bt_1",
                "status": "COMPLETED",
            },
        ]
        mock_uow = MagicMock()
        mock_bt_repo = MagicMock()
        mock_uow.get_repository.return_value = mock_bt_repo
        mock_bt_repo.get_result_metrics.return_value = {
            "percentage_return": 10.0,
            "strategy_attribution": {
                "BuyStrat1": {
                    "total_trades": 2,
                    "winning_trades": 1,
                    "losing_trades": 1,
                    "win_rate_pct": 50.0,
                    "net_pnl": 100.0,
                    "profit_factor": 1.5,
                    "avg_return_pct": 0.05,
                    "max_win": 150.0,
                    "max_loss": -50.0,
                }
            },
        }

        report = ExperimentApplicationService._compute_experiment_report(mock_uow, spec, bindings)

        assert "BuyStrat1" in report["strategy_attribution"]
        assert "SellStrat2" in report["strategy_attribution"]
        assert "IdleStrat3" in report["strategy_attribution"]
        assert report["strategy_attribution"]["SellStrat2"]["action"] == "SELL"
        assert report["strategy_attribution"]["IdleStrat3"]["total_trades"] == 0
        assert report["strategy_attribution"]["SellStrat2"]["weight"] == 1.5
        assert report["strategy_attribution"]["IdleStrat3"]["weight"] == 0.5
        assert report["strategy_weights"]["SellStrat2"] == 1.5
        matrix = report["strategy_combination_matrix"]["matrix"]
        assert len(matrix) == 3
        assert matrix["BuyStrat1"]["BuyStrat1"] == 1.0

    def test_current_candidate_reloads_weights_from_branch_head_commit(self):
        cand = ExperimentCandidate(
            candidate_id="cand_current",
            name="Current Configuration",
            candidate_type=CandidateType.CURRENT_CONFIG,
            strategy_weights={"TrendBreakoutBuy": 1.0},
        )
        self.mock_vcs.resolve_commit_hash.return_value = "commit_sha_branch_updated"
        with patch.object(
            self.service,
            "_load_asset_strategy_weights",
            return_value={"TrendBreakoutBuy": 2.3, "OversoldRecoverySell": 4.0},
        ) as mock_load:
            commit = self.service._resolve_candidate_commit("exp-branch-1", "BTC_USD", cand)
            mock_load.assert_called_once_with("commit_sha_branch_updated", "BTC_USD")
            assert commit == "commit_sha_branch_updated"
            assert cand.strategy_weights["TrendBreakoutBuy"] == 2.3
            assert cand.strategy_weights["OversoldRecoverySell"] == 4.0

    def test_disabled_strategies_are_filtered_from_candidate_variants(self):
        enabled_strat = MagicMock(name="EnabledStrat")
        enabled_strat.name = "EnabledStrat"
        enabled_strat.enabled = True
        enabled_strat.weight = 1.0
        enabled_strat.model_copy.side_effect = lambda update: MagicMock(
            name="EnabledStrat", weight=update.get("weight", 1.0), enabled=True
        )

        disabled_strat = MagicMock(name="DisabledStrat")
        disabled_strat.name = "DisabledStrat"
        disabled_strat.enabled = False
        disabled_strat.weight = 0.5
        disabled_strat.model_copy.side_effect = lambda update: MagicMock(
            name="DisabledStrat", weight=update.get("weight", 0.5), enabled=False
        )

        cand = ExperimentCandidate(
            candidate_id="cand_random_42",
            name="Random Control",
            candidate_type=CandidateType.RANDOM_CONTROL,
            random_seed=42,
        )

        ExperimentApplicationService._apply_candidate_weights(
            cand, [enabled_strat, disabled_strat]
        )

        assert "EnabledStrat" in cand.strategy_weights
        assert "DisabledStrat" not in cand.strategy_weights

    def test_dispatch_candidate_runs_isolates_variants_on_frozen_assets(self):
        from api.interfaces.asset import Asset
        from api.interfaces.asset_schedule import AssetSchedule
        from api.interfaces.timeframe import Timeframe
        from api.interfaces.trade_action import TradeAction
        from src.configuration.strategy_config import StrategyConfig, StrategyType
        from src.configuration.trading_config import TradingConfig
        from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
        from src.trading.consensus.consensus_factor import ConsensusFactor

        base_config = TradingConfig(
            assets=[
                Asset(
                    base_ticker_symbol="BTC",
                    quote_ticker_symbol="USD",
                    quote_decimals=2,
                    name="Bitcoin",
                    exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
                    min_quantity=0.001,
                    quantity_decimals=5,
                    schedule=AssetSchedule.EVERY_MINUTE,
                    candles_timeframe=Timeframe.MIN1,
                    consensus=ConsensusFactor(buy=0.7, sell=0.4),
                    strategies=[
                        StrategyConfig(
                            name="BreakoutBuy",
                            type=StrategyType.DYNAMIC,
                            action=TradeAction.BUY,
                            expression="close > sma(20)",
                            enabled=False,
                            weight=1.0,
                        ),
                        StrategyConfig(
                            name="TrendBreakoutBuy",
                            type=StrategyType.DYNAMIC,
                            action=TradeAction.BUY,
                            expression="close > sma(50)",
                            enabled=True,
                            weight=2.3,
                        ),
                    ],
                )
            ]
        )

        # Stateful in-memory VCS fake to verify candidate isolation & ref hygiene
        refs: dict[str, str] = {"refs/heads/backtest/exp-iso": "base_commit_001"}
        commits: dict[str, dict] = {"base_commit_001": base_config.model_dump(mode="json")}
        counter = {"n": 0}

        def fake_resolve(ref: str) -> str:
            return refs[ref]

        def fake_checkout(commit_hash: str) -> dict:
            return commits[commit_hash]

        def fake_branch(name: str, from_ref: str = "HEAD") -> None:
            refs[name] = refs.get(from_ref, from_ref)

        def fake_commit(content: TradingConfig, author: str, message: str, ref: str) -> MagicMock:
            counter["n"] += 1
            h = f"cand_commit_{counter['n']:03d}"
            commits[h] = content.model_dump(mode="json")
            refs[ref] = h
            c = MagicMock()
            c.hash = h
            return c

        self.mock_vcs.resolve_commit_hash.side_effect = fake_resolve
        self.mock_vcs.checkout.side_effect = fake_checkout
        self.mock_vcs.branch.side_effect = fake_branch
        self.mock_vcs.commit.side_effect = fake_commit

        self.mock_bt_app.pin_market_data_snapshot.return_value = "snapshot:abc123"
        dispatched_specs = []

        def fake_start_bt(bt_spec):
            dispatched_specs.append(bt_spec)
            sess = MagicMock()
            sess.id = f"bt_{len(dispatched_specs)}"
            return sess

        self.mock_bt_app.start_backtest_run.side_effect = fake_start_bt

        spec = ExperimentSpec(
            name="Anomaly BTC_USD Isolation Test",
            ticker_symbol="BTC_USD",
            base_commit_hash="base_commit_001",
            branch_id="exp-iso",
            test_selection=TestSelection.BACKTEST_ONLY,
            candidates=[
                ExperimentCandidate(
                    candidate_id="cand_current",
                    name="Current",
                    candidate_type=CandidateType.CURRENT_CONFIG,
                ),
                ExperimentCandidate(
                    candidate_id="cand_equal_weight",
                    name="Equal Weight",
                    candidate_type=CandidateType.EQUAL_WEIGHT,
                ),
                ExperimentCandidate(
                    candidate_id="cand_reenable",
                    name="Re-enable Disabled",
                    candidate_type=CandidateType.CUSTOM_COMBINATION,
                    strategy_enabled_overrides={"BreakoutBuy": True},
                ),
                ExperimentCandidate(
                    candidate_id="cand_tuned",
                    name="Tuned Thresholds",
                    candidate_type=CandidateType.CUSTOM_COMBINATION,
                    strategy_weights={"TrendBreakoutBuy": 1.95},
                    consensus_override={"buy": 0.56},
                ),
                ExperimentCandidate(
                    candidate_id="cand_add",
                    name="Add Complementary",
                    candidate_type=CandidateType.CUSTOM_COMBINATION,
                    strategies_to_add=[
                        {
                            "name": "TrendFollowingBuy",
                            "type": "DYNAMIC",
                            "action": "BUY",
                            "weight": 1.0,
                            "enabled": True,
                            "expression": "sma(20) > sma(50) and close > sma(20)",
                        }
                    ],
                ),
            ],
        )

        bindings = self.service._dispatch_candidate_runs(spec, spec.candidates)

        assert len(bindings) == 5
        commit_hashes = [c.candidate_commit_hash for c in spec.candidates]
        # Every candidate gets a distinct commit hash; branch ref stays at base commit
        assert commit_hashes[0] == "base_commit_001"
        assert len(set(commit_hashes)) == 5
        assert refs["refs/heads/backtest/exp-iso"] == "base_commit_001"

        # Verify each candidate's committed config has ONLY its own mutations (no bleeding)
        eq_cfg = TradingConfig.model_validate(commits[commit_hashes[1]])
        assert {s.name: s.weight for s in eq_cfg.assets[0].strategies} == {
            "BreakoutBuy": 1.0,
            "TrendBreakoutBuy": 1.0,
        }

        reenable_cfg = TradingConfig.model_validate(commits[commit_hashes[2]])
        reenable_strats = {s.name: s for s in reenable_cfg.assets[0].strategies}
        assert reenable_strats["BreakoutBuy"].enabled is True
        # Must NOT inherit cand_equal_weight's weight=1.0 for TrendBreakoutBuy
        assert reenable_strats["TrendBreakoutBuy"].weight == 2.3

        tuned_cfg = TradingConfig.model_validate(commits[commit_hashes[3]])
        tuned_strats = {s.name: s for s in tuned_cfg.assets[0].strategies}
        assert tuned_cfg.assets[0].consensus.buy == 0.56
        assert tuned_cfg.assets[0].consensus.sell == 0.4
        assert tuned_strats["TrendBreakoutBuy"].weight == 1.95
        # Must NOT inherit cand_reenable's enabled=True for BreakoutBuy
        assert tuned_strats["BreakoutBuy"].enabled is False

        add_cfg = TradingConfig.model_validate(commits[commit_hashes[4]])
        add_names = {s.name for s in add_cfg.assets[0].strategies}
        assert "TrendFollowingBuy" in add_names
        # Must NOT inherit cand_tuned's consensus override
        assert add_cfg.assets[0].consensus.buy == 0.7

        # Verify market data snapshot was pinned once and shared across all 5 candidates
        self.mock_bt_app.pin_market_data_snapshot.assert_called_once()
        assert all(s.data_source.dataset_id == "snapshot:abc123" for s in dispatched_specs)

    def test_single_callback_subscription_deduplicates_experiment_run_event(self):
        from src.events.agent_events import AgentExperimentRunRequestedEvent
        from src.events.message_event_bus import CallbackSubscription, MessageEventBus

        bus = MessageEventBus()
        received = []
        sub = CallbackSubscription(received.append)
        for event_type in (
            AgentExperimentRunRequestedEvent.EVENT_TYPE,
            "AgentExperimentRunRequestedEvent",
        ):
            bus.subscribe(event_type, sub)

        bus.publish(
            AgentExperimentRunRequestedEvent(
                approval_id="appr_123",
                asset="BTC_USD",
                experiment_config={"ticker_symbol": "BTC_USD"},
            )
        )

        assert len(received) == 1
        assert received[0].approval_id == "appr_123"
