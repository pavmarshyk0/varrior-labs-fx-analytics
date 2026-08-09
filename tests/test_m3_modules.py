import unittest
from datetime import UTC, datetime, timedelta

from analytics.meta_model.meta_label_conformal import InsufficientSampleError, MetaLabelConformal
from analytics.context.event_time_hazard import (
    EventTimeHazardModule,
    HistoricalTemporalOutcome,
    TemporalContext,
    TemporalPosteriorTable,
)
from analytics.microstructure.tick_burst_intensity import TickBurstIntensity
from analytics.microstructure.tick_state_classifier import (
    LevelExcursionDetector,
    QuotePressureFeatureExtractor,
    SessionRobustBaseline,
    TickStateClassifier,
    TickStateModule,
)
from analytics.regime.hsmm_regime_filter import HSMMRegimeFilter
from analytics.regime.online_regime_guard import M5Observation, OnlineRegimeGuard, OnlineRobustScaler
from demo_beta.contracts import Candidate, Direction, Tick
from engine.costs_model import CostBucket, CostsModel
from engine.walk_forward import EventInterval, purged_walk_forward_splits
from engine.fold_baselines import BaselineEvent, fit_walk_forward_session_baselines
from engine.research_statistics import TradeObservation, block_bootstrap_expectancy_ci, performance_statistics
from engine.ablation import preregistered_ablation_matrix
from engine.research_report import ArmReport, render_research_report


BASE = datetime(2026, 8, 5, 9, 15, tzinfo=UTC)
T0 = int(BASE.timestamp() * 1000)


def candidate() -> Candidate:
    return Candidate(
        candidate_id="micro-1",
        direction=Direction.LONG,
        entry=1.1001,
        stop_loss=1.0991,
        take_profit=1.1031,
        entry_available_at=BASE,
        max_holding=timedelta(minutes=30),
        level=1.1000,
        atr_m5=0.0010,
    )


class TickStateTests(unittest.TestCase):
    def test_excursion_threshold_uses_max_atr_and_spread(self):
        ticks = [
            Tick(T0, 1.09995, 1.10005, 6),
            Tick(T0 + 1000, 1.10020, 1.10030, 6),
        ]
        event = LevelExcursionDetector().detect(ticks, 1.1000, Direction.LONG, 0.0010)
        self.assertIsNotNone(event)
        self.assertAlmostEqual(event.threshold, 0.00015)

    def test_robust_session_baseline_is_not_full_sample_global_state(self):
        baseline = SessionRobustBaseline()
        baseline.fit(
            [{"tick_intensity": 5.0, "spread_pips": 1.0}, {"tick_intensity": 7.0, "spread_pips": 1.2}],
            ["LONDON", "LONDON"],
        )
        self.assertEqual(baseline.sample_size("LONDON"), 2)
        self.assertEqual(baseline.sample_size("NY"), 0)

    def test_feature_extractor_and_classifier_are_finite(self):
        ticks = [
            Tick(T0, 1.10000, 1.10010, 6),
            Tick(T0 + 1000, 1.09970, 1.09980, 6),
            Tick(T0 + 16_000, 1.09990, 1.10000, 6),
            Tick(T0 + 30_000, 1.10010, 1.10020, 6),
        ]
        event = LevelExcursionDetector().detect(ticks, 1.1000, Direction.LONG, 0.0010)
        self.assertIsNotNone(event)
        features = QuotePressureFeatureExtractor().compute(event)
        result = TickStateClassifier().classify(features)
        self.assertAlmostEqual(sum(result.state_probabilities.values()), 1.0)
        self.assertGreaterEqual(result.signal, -1.0)
        self.assertLessEqual(result.signal, 1.0)

    def test_module_never_changes_candidate_direction(self):
        ticks = [
            Tick(T0, 1.09995, 1.10005, 6),
            Tick(T0 + 1000, 1.10020, 1.10030, 6),
            Tick(T0 + 17_000, 1.10025, 1.10035, 6),
        ]
        output = TickStateModule().evaluate(candidate(), ticks)
        self.assertIs(output.direction, Direction.LONG)
        self.assertTrue(output.candidate_direction_unchanged)


class BurstTests(unittest.TestCase):
    def test_directional_burst_responds_to_up_ticks(self):
        model = TickBurstIntensity()
        readings = model.transform(
            [Tick(T0 + i * 100, 1.1000 + i * 0.0001, 1.1001 + i * 0.0001) for i in range(5)]
        )
        self.assertGreater(readings[-1].directional_excitation, 0.0)


class RegimeTests(unittest.TestCase):
    def _observation(self, i: int, multiplier: float = 1.0) -> M5Observation:
        return M5Observation(
            timestamp=BASE + timedelta(minutes=5 * i),
            realized_volatility_5m=0.0003 * multiplier,
            realized_volatility_30m=0.0006 * multiplier,
            median_spread_pips_5m=0.8 * multiplier,
            spread_p95_pips_5m=1.3 * multiplier,
            tick_intensity_5m=400.0 * multiplier,
            absolute_return_5m=0.0002 * multiplier,
            missing_tick_ratio=0.001,
        )

    def test_shadow_guard_never_applies_suggested_multiplier(self):
        guard = OnlineRegimeGuard(scaler=OnlineRobustScaler(min_history=3, max_history=20))
        for i in range(3):
            guard.evaluate(self._observation(i))
        output = guard.evaluate(self._observation(3, multiplier=10.0))
        self.assertEqual(output.model_status, "SHADOW")
        self.assertEqual(output.applied_risk_multiplier, 1.0)

    def test_hsmm_research_filter_requires_duration_before_switch(self):
        model = HSMMRegimeFilter(minimum_duration_bars=2)
        first = model.update(3.0, 3.0)
        second = model.update(3.0, 3.0)
        self.assertEqual(first.regime, "NORMAL")
        self.assertEqual(second.regime, "HIGH_STRESS")
        self.assertEqual(second.model_status, "RESEARCH")


class ValidationInfrastructureTests(unittest.TestCase):
    def test_meta_model_refuses_small_sample(self):
        model = MetaLabelConformal(minimum_candidates=800)
        with self.assertRaises(InsufficientSampleError):
            model.fit([[0.0], [1.0]], [0, 1], [[0.5]], [1])

    def test_walk_forward_purges_overlap_and_embargo(self):
        events = [
            EventInterval(BASE + timedelta(hours=i), BASE + timedelta(hours=i, minutes=30))
            for i in range(12)
        ]
        splits = purged_walk_forward_splits(
            events,
            minimum_train_size=4,
            validation_size=2,
            embargo=timedelta(minutes=15),
        )
        self.assertTrue(splits)
        for split in splits:
            cutoff = split.validation_start - timedelta(minutes=15)
            self.assertTrue(all(events[i].label_end < cutoff for i in split.train_indices))

    def test_cost_model_does_not_have_constant_spread_charge(self):
        model = CostsModel(fallback=CostBucket(0.2, 0.3, 100))
        fills = model.fill_assumption("LONDON", "NORMAL", "LONG")
        self.assertEqual(fills.entry_slippage_pips, 0.2)
        self.assertFalse(hasattr(fills, "spread_pips"))

    def test_session_baseline_is_fit_only_on_purged_walk_forward_train_indices(self):
        events = [BaselineEvent(
            EventInterval(BASE + timedelta(hours=i), BASE + timedelta(hours=i, minutes=10)),
            "LONDON", {"spread_pips": float(i + 1)},
        ) for i in range(8)]
        folds = fit_walk_forward_session_baselines(
            events, minimum_train_size=3, validation_size=2, embargo=timedelta(0),
        )
        self.assertTrue(folds)
        first = folds[0]
        self.assertEqual(first.fitted_indices, first.split.train_indices)
        self.assertLess(first.baseline.stat("LONDON", "spread_pips").median, 4.0)
        self.assertNotIn(first.split.validation_indices[0], first.fitted_indices)


class TemporalPosteriorTests(unittest.TestCase):
    def test_sparse_bucket_is_shrunk_and_cannot_drive_trade(self):
        london = TemporalContext("LONDON", "NONE", "EU_US_ALIGNED", "NORMAL")
        ny = TemporalContext("NY", "NONE", "EU_US_ALIGNED", "NORMAL")
        outcomes = [
            HistoricalTemporalOutcome(BASE + timedelta(days=i), london, 0.2 if i % 2 == 0 else -0.1)
            for i in range(10)
        ] + [HistoricalTemporalOutcome(BASE + timedelta(days=20), ny, -3.0)]
        table = TemporalPosteriorTable(minimum_bucket_size=30)
        table.fit(outcomes)
        estimate = table.query(ny)
        self.assertFalse(estimate.independently_actionable)
        self.assertLess(estimate.shrinkage_weight, 0.1)

    def test_time_module_stays_neutral_without_prospective_approval(self):
        context = TemporalContext("LONDON", "NONE", "EU_US_ALIGNED", "NORMAL")
        table = TemporalPosteriorTable(minimum_bucket_size=2)
        table.fit(
            [HistoricalTemporalOutcome(BASE + timedelta(days=i), context, -1.0) for i in range(4)]
        )
        output = EventTimeHazardModule(table, prospective_directional_approval=False).evaluate(candidate(), context)
        self.assertEqual(output.signal, 0.0)
        self.assertEqual(output.decision_effect.value, "NEUTRAL")


class ResearchStatisticsTests(unittest.TestCase):
    def test_trade_statistics_include_drawdown_streak_frequency_and_excursions(self):
        trades = [
            TradeObservation(BASE, 1.0, -0.2, 1.2),
            TradeObservation(BASE + timedelta(days=1), -1.0, -1.1, 0.3),
            TradeObservation(BASE + timedelta(days=2), -0.5, -0.7, 0.2),
            TradeObservation(BASE + timedelta(days=7), 2.0, -0.1, 2.1),
        ]
        stats = performance_statistics(trades)
        self.assertEqual(stats.longest_losing_streak, 2)
        self.assertAlmostEqual(stats.maximum_drawdown_r, 1.5)
        self.assertAlmostEqual(stats.expectancy_r, 0.375)
        self.assertAlmostEqual(stats.frequency_per_week, 4.0)

    def test_block_bootstrap_is_deterministic_and_returns_95_ci(self):
        one = block_bootstrap_expectancy_ci([1.0, -1.0, 2.0, -0.5], block_size=2, samples=100, seed=9)
        two = block_bootstrap_expectancy_ci([1.0, -1.0, 2.0, -0.5], block_size=2, samples=100, seed=9)
        self.assertEqual(one, two)
        self.assertLessEqual(one.lower_95, one.point_estimate)
        self.assertGreaterEqual(one.upper_95, one.point_estimate)


class ResearchReportingTests(unittest.TestCase):
    def test_preregistered_matrix_contains_pairs_full_and_full_minus_one(self):
        arms = preregistered_ablation_matrix()
        self.assertEqual(arms[0].name, "Baseline")
        self.assertIn("Tick+Time", [arm.name for arm in arms])
        self.assertIn("Full-minus-Regime", [arm.name for arm in arms])
        self.assertTrue(all(arm.execution_authority == "NONE" for arm in arms))

    def test_research_report_is_oos_lineage_aware_and_non_promotional(self):
        baseline = preregistered_ablation_matrix()[0]
        report = render_research_report([ArmReport(
            baseline, (TradeObservation(BASE, 1.0, -0.2, 1.1), TradeObservation(BASE + timedelta(days=7), -1.0, -1.0, 0.2)),
            ("lineage-1",),
        )], bootstrap_block_size=1, bootstrap_samples=50)
        self.assertIn("lineage-1", report)
        self.assertIn("RESEARCH", report)
        self.assertIn("Baseline", report)


if __name__ == "__main__":
    unittest.main()
