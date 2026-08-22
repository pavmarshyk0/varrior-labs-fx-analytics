import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from engine.event_studies import (
    CONFIRMATION_END,
    Event,
    generate_predeclared_events,
    run_event_studies_from_dataset,
    summarize_events,
)
from engine.exit_ablation_runner import BarDataset


def bar(start, mid=1.1000, close=None, half_range=0.0002, ticks=100,
        spread_p95=0.2, flags=()):
    close = mid if close is None else close
    spread = 0.0001
    high = max(mid, close) + half_range
    low = min(mid, close) - half_range
    return {
        "bar_start": start.isoformat(),
        "bar_end": (start + timedelta(minutes=5)).isoformat(),
        "bid_open": mid - spread / 2,
        "ask_open": mid + spread / 2,
        "bid_close": close - spread / 2,
        "ask_close": close + spread / 2,
        "bid_high": high - spread / 2,
        "ask_high": high + spread / 2,
        "bid_low": low - spread / 2,
        "ask_low": low + spread / 2,
        "tick_count": ticks,
        "spread_pips_p95": spread_p95,
        "quality_flags": list(flags),
    }


class EventStudyTests(unittest.TestCase):
    def test_session_opens_are_dst_aware(self):
        # 08:00 London is 08:00 UTC in winter and 07:00 UTC in summer.
        rows = [bar(datetime(2025, 1, 2, 8, tzinfo=UTC)),
                bar(datetime(2025, 7, 2, 7, tzinfo=UTC))]
        events = generate_predeclared_events(rows)
        self.assertEqual([event.event_id for event in events].count("LONDON_OPEN"), 2)

    def test_pdh_break_uses_most_recent_completed_trading_day_once(self):
        # 22:00 UTC is 17:00 New York in winter.
        base = datetime(2025, 1, 1, 22, tzinfo=UTC)
        rows = [bar(base + timedelta(minutes=5 * i), 1.1000, half_range=0.0002)
                for i in range(288)]
        next_day = base + timedelta(days=1)
        rows.extend([
            bar(next_day, 1.1000, half_range=0.0001),
            bar(next_day + timedelta(minutes=5), 1.1005, close=1.1006, half_range=0.0001),
            bar(next_day + timedelta(minutes=10), 1.1007, close=1.1008, half_range=0.0001),
        ])
        events = generate_predeclared_events(rows)
        pdh = [event for event in events if event.event_id == "PDH_FIRST_BREAK"]
        self.assertEqual(len(pdh), 1)
        self.assertEqual(pdh[0].orientation, 1)
        self.assertEqual(pdh[0].entry_index, 290)

    def test_expanded_asian_range_becomes_available_only_at_0800_utc(self):
        base = datetime(2025, 1, 6, tzinfo=UTC)
        rows = [bar(base + timedelta(minutes=5 * i), 1.1000, half_range=0.0002)
                for i in range(96)]
        rows.extend([
            bar(base + timedelta(hours=8), 1.1004, close=1.1005, half_range=0.0001),
            bar(base + timedelta(hours=8, minutes=5), 1.1005),
        ])
        events = generate_predeclared_events(rows)
        breaks = [event for event in events if event.event_id == "ASIAN_HIGH_FIRST_BREAK"]
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0].timestamp, base + timedelta(hours=8, minutes=5))

    def test_predeclared_state_transitions_are_generated(self):
        base = datetime(2025, 1, 6, tzinfo=UTC)
        rows = [bar(base + timedelta(minutes=5 * i), half_range=0.001)
                for i in range(300)]
        # A coherent, high-intensity move also supplies the trend/microstructure proxy cases.
        price = 1.1000
        for i in range(6):
            close = price + 0.0004
            rows.append(bar(base + timedelta(minutes=5 * (300 + i)), price, close,
                            half_range=0.00002, ticks=1000 if i == 0 else 100,
                            spread_p95=0.1))
            price = close
        # Twelve tight bars force a causal compression transition.
        for i in range(6, 20):
            rows.append(bar(base + timedelta(minutes=5 * (300 + i)), price,
                            half_range=0.00002))
        events = generate_predeclared_events(rows)
        ids = {event.event_id for event in events}
        self.assertIn("EFFICIENT_TREND_IMPULSE", ids)
        self.assertIn("HIGH_INTENSITY_COHERENT_BAR_PROXY", ids)
        self.assertIn("VOLATILITY_COMPRESSION_TRANSITION", ids)

    def test_range_deviation_is_oriented_back_to_the_mean(self):
        base = datetime(2025, 1, 6, tzinfo=UTC)
        rows = [bar(base + timedelta(minutes=5 * i), half_range=0.001)
                for i in range(300)]
        rows.append(bar(base + timedelta(minutes=5 * 300), 1.1000, close=1.1008,
                        half_range=0.0001))
        rows.append(bar(base + timedelta(minutes=5 * 301), 1.1008))
        events = generate_predeclared_events(rows)
        mean_events = [event for event in events
                       if event.event_id == "RANGE_DEVIATION_MEAN_REVERSION"]
        self.assertTrue(mean_events)
        self.assertEqual(mean_events[-1].orientation, -1)

    def test_locked_holdout_never_reads_prices(self):
        timestamp = CONFIRMATION_END + timedelta(days=1)
        rows = [{"bar_start": timestamp.isoformat(), "quality_flags": []}]
        event = Event("LONDON_OPEN", timestamp, 0, 1, "DIRECTIONAL", {})
        result = summarize_events(rows, [event])
        locked = result["LONDON_OPEN"]["periods"]["LOCKED_HOLDOUT"]
        self.assertEqual(locked, {"event_count": 1, "outcomes_computed": False})

    def test_artifact_marks_non_executable_and_locked(self):
        timestamp = CONFIRMATION_END + timedelta(days=1)
        rows = [bar(timestamp)]
        dataset = BarDataset({"M5": rows}, {"dataset_fingerprint": "test"})
        with tempfile.TemporaryDirectory() as directory:
            root = run_event_studies_from_dataset(dataset, directory)
            artifact = json.loads((Path(root) / "event_studies.json").read_text())
        self.assertEqual(artifact["schema_version"], "event-studies/v2")
        self.assertEqual(artifact["research_mode"], "NON_EXECUTABLE_EVENT_STUDY")
        self.assertFalse(artifact["automatic_promotion"])
        self.assertFalse(artifact["boundaries"]["holdout_outcomes_computed"])


if __name__ == "__main__":
    unittest.main()
