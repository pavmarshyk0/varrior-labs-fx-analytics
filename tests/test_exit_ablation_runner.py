import unittest
from datetime import UTC, datetime, timedelta

from engine.exit_ablation_runner import (BarDataset, BaselineCandidateGenerator, CandidateEvent, Evaluation, RunnerConfig,
                                         _closed_bar, evaluate_event)
from engine.costs_model import CostsModel
from engine.trade_research import ExitPolicy, InvalidationKind, StructuralInvalidation
from demo_beta.contracts import Direction

def bar(start, *, up=True, flags=()):
    t = start.isoformat().replace('+00:00', 'Z'); end = (start + timedelta(minutes=5)).isoformat().replace('+00:00', 'Z')
    return {'bar_start': t, 'bar_end': end, 'symbol': 'EURUSD', 'bid_open': 1.1, 'bid_close': 1.1002 if up else 1.0998,
            'bid_high': 1.1005, 'bid_low': 1.0995, 'ask_open': 1.1001, 'ask_close': 1.1003 if up else 1.0999,
            'ask_high': 1.1006, 'ask_low': 1.0996, 'quality_flags': list(flags)}

class ExitAblationRunnerTests(unittest.TestCase):
    def test_htf_alignment_only_uses_completed_bar(self):
        time = datetime(2026, 1, 1, 10, 4, 59, tzinfo=UTC)
        rows = [bar(datetime(2026, 1, 1, 9, 45, tzinfo=UTC)), bar(datetime(2026, 1, 1, 10, 0, tzinfo=UTC))]
        self.assertEqual(_closed_bar(rows, time)['bar_end'], rows[0]['bar_end'])

    def test_generator_is_deterministic_and_excludes_invalid_current_bar(self):
        base = datetime(2026, 1, 1, tzinfo=UTC)
        m5 = [bar(base + timedelta(minutes=5*i), flags=('EXTREME_SPREAD',) if i == 12 else ()) for i in range(40)]
        m15 = [bar(base + timedelta(minutes=15*i)) for i in range(14)]; h1 = [bar(base + timedelta(hours=i)) for i in range(4)]
        data = BarDataset({'M5': m5, 'M15': m15, 'H1': h1}, {'symbol': 'EURUSD'})
        generated = BaselineCandidateGenerator(RunnerConfig(atr_lookback=3, candidate_stride_bars=3)).generate(data)
        self.assertEqual([x.candidate_id for x in generated], [x.candidate_id for x in BaselineCandidateGenerator(RunnerConfig(atr_lookback=3, candidate_stride_bars=3)).generate(data)])
        self.assertTrue(all('T010500Z' not in x.candidate_id for x in generated))

    def test_ambiguous_bar_is_conservative_and_cost_reduces_result(self):
        timestamp = datetime(2026, 1, 1, 10, tzinfo=UTC)
        stop = StructuralInvalidation(Direction.LONG, 1.1, 1.099, 'X', 'M5', 0, InvalidationKind.SWING)
        event = CandidateEvent('x', timestamp, 'EUR_USD', Direction.LONG, 'S', 1.1, stop, 'M5', 'BULL', 'LONDON', {}, (), True, 'VALID')
        future = [dict(bar(timestamp), bid_low=1.0989, bid_high=1.1041, ask_high=1.1042, ask_low=1.099)]
        out = evaluate_event(event, future, ExitPolicy.FIXED_RR, 'BASELINE_1X', CostsModel(), RunnerConfig(), 0)
        self.assertEqual(out.outcome, 'AMBIGUOUS_CONSERVATIVE_STOP')
        self.assertLess(out.net_r, out.gross_r)

if __name__ == '__main__': unittest.main()
