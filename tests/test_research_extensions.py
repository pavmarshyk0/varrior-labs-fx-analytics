import unittest
from datetime import UTC, datetime, timedelta

from demo_beta.contracts import Direction
from engine.costs_model import CostBucket, CostsModel, ExecutionRegime
from engine.governance import ExecutionMonitorConfig, ExecutionObservation, rolling_execution_monitor
from engine.research_statistics import target_before_stop_probabilities
from engine.trade_research import (ConfidenceTier, ExitPolicy, InvalidationKind, ReliabilityConfig, ResearchMode,
                                   StructuralInvalidation, TargetType, choose_exit_plan, expected_value,
                                   feasibility_gates, fixed_r_target, shrunk_mean)
from engine.walk_forward import EventInterval, lock_final_holdout


class ResearchExtensionTests(unittest.TestCase):
    def test_joint_stress_is_coupled_and_not_a_flat_cost_multiplier(self):
        model = CostsModel(fallback=CostBucket(.2, .3, 10, stop_slippage_pips=.4, event_slippage_pips=.5))
        normal = model.estimate_r("LDN", "NORMAL", "LONG", risk_price=.001)
        joint = model.estimate_r("LDN", "NORMAL", "LONG", risk_price=.001,
                                 regime=ExecutionRegime.JOINT_EXECUTION_STRESS, stopped=True)
        self.assertGreater(joint.total_r, normal.total_r)
        self.assertNotEqual(joint.entry_slippage_r / normal.entry_slippage_r, joint.exit_slippage_r / normal.exit_slippage_r)
        self.assertIn("BASELINE_1.25X", model.stress_matrix("LDN", "NORMAL", "LONG", risk_price=.001))

    def test_structural_stop_and_fixed_3r_baseline_are_valid(self):
        invalidation = StructuralInvalidation(Direction.LONG, 1.1, 1.099, "SWING_LOW", "M5", 1, InvalidationKind.SWING)
        target = fixed_r_target(Direction.LONG, invalidation.entry, invalidation.stop_distance)
        plan = choose_exit_plan(ExitPolicy.FIXED_RR, [target])
        self.assertTrue(invalidation.valid)
        self.assertEqual(plan.targets[0].target_type, TargetType.FIXED_R)

    def test_path_order_prevents_mfe_from_becoming_optimistic_hit(self):
        stats = target_before_stop_probabilities([[1.0, -1.0], [-1.0, 3.0], [3.0, -1.0]])
        self.assertAlmostEqual(stats.probabilities_before_stop[3.0], 1 / 3)

    def test_shrinkage_and_strict_ci_gate(self):
        self.assertLess(shrunk_mean(1.0, 1, 0.0), 0.1)
        reliability = ReliabilityConfig()
        ev = expected_value(win_probability=.6, gross_win_r=1, gross_loss_r=-1, cost_drag_r=.05,
                            sample_size=20, reliability=reliability, setup="S", regime="R", exit_policy=ExitPolicy.DYNAMIC_RR)
        invalidation = StructuralInvalidation(Direction.LONG, 1.1, 1.099, "X", "M5", 1)
        result = feasibility_gates(valid_data=True, invalidation=invalidation, risk_fraction=.005, ev=ev,
                                   stress_net_expectancies={"BASELINE_1.25X": .01}, mode=ResearchMode.RESEARCH)
        self.assertEqual(ev.confidence_tier, ConfidenceTier.INSUFFICIENT)
        self.assertIn("INSUFFICIENT_SAMPLE", result.reasons)

    def test_locked_holdout_and_execution_pause(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        holdout = lock_final_holdout([EventInterval(base + timedelta(days=i), base + timedelta(days=i, hours=1)) for i in range(5)], holdout_size=2)
        self.assertEqual(holdout.indices, (3, 4))
        observations = [ExecutionObservation(2, 1, .2, .01) for _ in range(30)]
        result = rolling_execution_monitor(observations, config=ExecutionMonitorConfig(cost_gap_r_limit=.05))
        self.assertTrue(result.automatic_execution_pause)


if __name__ == "__main__":
    unittest.main()
