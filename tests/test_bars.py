import unittest
from datetime import UTC, datetime, timedelta

from demo_beta.contracts import Tick
from demo_beta.data.bars import MT5BarBuilder


def tick(at, bid, ask):
    return Tick(int(at.timestamp() * 1000), bid, ask, 6)


class BarConstructionTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 7, 6, 10, tzinfo=UTC)
        self.builder = MT5BarBuilder()

    def test_m5_boundaries_ohlc_bid_ask_and_tick_metadata(self):
        ticks = [tick(self.start, 1.1, 1.1002), tick(self.start + timedelta(minutes=4), 1.099, 1.1005),
                 tick(self.start + timedelta(minutes=5), 1.101, 1.1011)]
        bars, report = self.builder.build(ticks, self.start, self.start + timedelta(minutes=10), ("M5",))
        self.assertEqual(len(bars["M5"]), 2)
        first, second = bars["M5"]
        self.assertEqual(first["tick_count"], 2); self.assertEqual(first["bid_open"], 1.1); self.assertEqual(first["bid_low"], 1.099)
        self.assertEqual(first["ask_high"], 1.1005); self.assertEqual(second["bid_open"], 1.101)
        self.assertEqual(first["first_tick_timestamp"], "2026-07-06T10:00:00Z")
        self.assertEqual(first["last_tick_timestamp"], "2026-07-06T10:04:00Z")
        self.assertEqual(report["m5_tick_count"], 3)

    def test_spreads_gap_flags_duplicates_and_repeatability(self):
        ticks = [tick(self.start, 1.1, 1.1), tick(self.start, 1.1, 1.1),
                 tick(self.start + timedelta(seconds=61), 1.1, 1.1006)]
        first = self.builder.build(ticks, self.start, self.start + timedelta(minutes=5), ("M5",))
        second = self.builder.build(ticks, self.start, self.start + timedelta(minutes=5), ("M5",))
        row = first[0]["M5"][0]
        self.assertEqual(first, second); self.assertEqual(row["tick_count"], 3)
        self.assertEqual(row["zero_spread_tick_count"], 2); self.assertEqual(row["max_intertick_gap_ms"], 61_000)
        self.assertIn("HAS_SUSPICIOUS_GAP", row["quality_flags"]); self.assertIn("ZERO_SPREAD_HEAVY", row["quality_flags"])
        self.assertIn("EXTREME_SPREAD", row["quality_flags"])

    def test_gap_ending_in_1600_bar_is_flagged(self):
        start = datetime(2026, 7, 24, 15, 55, tzinfo=UTC)
        ticks = [tick(start + timedelta(minutes=4, seconds=33, milliseconds=754), 1.1, 1.1001),
                 tick(start + timedelta(minutes=7, seconds=54, milliseconds=374), 1.1, 1.1001)]
        bars, _ = self.builder.build(ticks, start, start + timedelta(minutes=10), ("M5",))
        at_1600 = next(row for row in bars["M5"] if row["bar_start"] == "2026-07-24T16:00:00Z")
        self.assertIn("HAS_SUSPICIOUS_GAP", at_1600["quality_flags"])
        self.assertEqual(at_1600["max_intertick_gap_ms"], 200_620)
        self.assertEqual(at_1600["suspicious_gap_count"], 1)
        self.assertEqual(at_1600["suspicious_gap_observations"][0]["previous_tick_timestamp"], "2026-07-24T15:59:33.754000Z")

    def test_multiple_gaps_in_one_m5_bar_keep_count_and_propagate(self):
        ticks = [tick(self.start, 1.1, 1.1001), tick(self.start + timedelta(seconds=61), 1.1, 1.1001),
                 tick(self.start + timedelta(seconds=122), 1.1, 1.1001)]
        bars, report = self.builder.build(ticks, self.start, self.start + timedelta(hours=1), ("M5", "M15", "H1"))
        self.assertEqual(bars["M5"][0]["suspicious_gap_count"], 2)
        self.assertEqual(report["bars_with_suspicious_gaps"], 1)
        self.assertEqual(report["suspicious_gap_count"], 2)
        self.assertEqual(bars["M15"][0]["suspicious_gap_count"], 2)
        self.assertEqual(bars["H1"][0]["suspicious_gap_count"], 2)

    def test_normal_adjacent_and_weekend_transitions_are_not_suspicious(self):
        adjacent = [tick(self.start + timedelta(minutes=4, seconds=59), 1.1, 1.1001),
                    tick(self.start + timedelta(minutes=5), 1.1, 1.1001)]
        bars, _ = self.builder.build(adjacent, self.start, self.start + timedelta(minutes=10), ("M5",))
        self.assertEqual(sum(row["suspicious_gap_count"] for row in bars["M5"]), 0)
        friday = datetime(2026, 7, 3, 23, 55, tzinfo=UTC)
        weekend = [tick(friday + timedelta(minutes=4, seconds=50), 1.1, 1.1001),
                   tick(friday + timedelta(days=3, minutes=5), 1.1, 1.1001)]
        bars, _ = self.builder.build(weekend, friday, friday + timedelta(days=3, minutes=10), ("M5",))
        self.assertEqual(sum(row["suspicious_gap_count"] for row in bars["M5"]), 0)

    def test_empty_trading_and_weekend_intervals_have_no_synthetic_bars(self):
        ticks = [tick(self.start, 1.1, 1.1001), tick(self.start + timedelta(minutes=10), 1.1, 1.1001)]
        bars, report = self.builder.build(ticks, self.start, self.start + timedelta(minutes=15), ("M5",))
        self.assertEqual(len(bars["M5"]), 2); self.assertEqual(report["empty_expected_trading_intervals"], 1)
        saturday = datetime(2026, 7, 4, tzinfo=UTC)
        weekend, weekend_report = self.builder.build([], saturday, saturday + timedelta(minutes=15), ("M5",))
        self.assertEqual(weekend["M5"], []); self.assertEqual(weekend_report["expected_market_closure_intervals"], 3)
        self.assertEqual(weekend_report["empty_expected_trading_intervals"], 0)

    def test_m5_to_m15_to_h1_reconciles_exactly(self):
        ticks = [tick(self.start + timedelta(minutes=offset), 1.1 + offset / 10000, 1.1001 + offset / 10000)
                 for offset in (0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55)]
        bars, report = self.builder.build(ticks, self.start, self.start + timedelta(hours=1), ("M5", "M15", "H1"))
        self.assertEqual(len(bars["M5"]), 12); self.assertEqual(len(bars["M15"]), 4); self.assertEqual(len(bars["H1"]), 1)
        self.assertEqual(bars["H1"][0]["tick_count"], 12)
        self.assertEqual(report["cross_timeframe_reconciliation_failures"], [])
        self.assertEqual(report["ohlc_invariant_violations"], [])
