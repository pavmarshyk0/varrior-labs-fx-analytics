import unittest
import json
import tempfile
from pathlib import Path
from datetime import UTC, datetime, timedelta

from demo_beta.backtesting import ExecutableBidAskBacktester, FillAssumption
from demo_beta.analytics.context.event_time_hazard import (
    BenchmarkWindowRegistry,
    CalendarLeakageError,
    CalendarSnapshot,
    EconomicCalendarAdapter,
    Impact,
    MacroEvent,
    MarketClock,
    ScheduledMacroJumpGuard,
)
from demo_beta.analytics.contracts import DecisionEffect
from demo_beta.analytics.context.calendar_snapshot import (
    CalendarSnapshotValidationError, load_calendar_snapshot, post_jump_stabilisation_inputs,
)
from demo_beta.contracts import BacktestOutcome, Candidate, Direction, Tick
from demo_beta.data.mt5 import MT5TickCollector
from demo_beta.data.pipeline import HistoricalTickPipeline
from demo_beta.data.validation import DataQualityViolation, TickFeedValidator
from demo_beta.risk import RiskPolicy, RiskViolation


BASE = datetime(2026, 8, 5, 10, tzinfo=UTC)
T0 = int(BASE.timestamp() * 1000)


def long_candidate(**changes) -> Candidate:
    values = dict(
        candidate_id="long-1",
        direction=Direction.LONG,
        entry=1.1001,
        stop_loss=1.0991,
        take_profit=1.1031,
        entry_available_at=BASE,
        max_holding=timedelta(minutes=5),
        risk_fraction=0.005,
    )
    values.update(changes)
    return Candidate(**values)


def short_candidate() -> Candidate:
    return Candidate(
        candidate_id="short-1",
        direction=Direction.SHORT,
        entry=1.1000,
        stop_loss=1.1010,
        take_profit=1.0970,
        entry_available_at=BASE,
        max_holding=timedelta(minutes=5),
        risk_fraction=0.005,
    )


class RiskPolicyTests(unittest.TestCase):
    def test_accepts_rr_three_and_half_percent_risk(self):
        RiskPolicy().validate(long_candidate())

    def test_rejects_rr_below_three(self):
        with self.assertRaisesRegex(RiskViolation, "planned RR"):
            RiskPolicy().validate(long_candidate(take_profit=1.1030))

    def test_rejects_risk_above_one_percent(self):
        with self.assertRaisesRegex(RiskViolation, "risk_fraction"):
            RiskPolicy().validate(long_candidate(risk_fraction=0.0101))

    def test_rejects_wrong_level_order(self):
        with self.assertRaisesRegex(RiskViolation, "LONG requires"):
            RiskPolicy().validate(long_candidate(stop_loss=1.1010, take_profit=1.1040))


class TickValidationTests(unittest.TestCase):
    def test_clean_ticks_are_valid_and_spread_is_measured_in_pips(self):
        ticks = [
            Tick(1000, 1.1000, 1.1001, 6),
            Tick(1100, 1.1001, 1.1002, 6),
            Tick(1200, 1.1002, 1.1004, 6),
        ]
        report = TickFeedValidator().validate(ticks)
        self.assertTrue(report.valid)
        self.assertTrue(report.timestamp_monotonic)
        self.assertAlmostEqual(report.spread_median_pips, 1.0)

    def test_anomalies_are_reported_not_silently_removed(self):
        ticks = [
            Tick(1000, 1.1000, 1.1001, 6),
            Tick(900, 1.1002, 1.1001, 6),
            Tick(900, 1.1002, 1.1001, 6),
        ]
        report = TickFeedValidator().validate(ticks)
        self.assertEqual(report.tick_count, 3)
        self.assertFalse(report.valid)
        self.assertEqual(report.out_of_order_count, 1)
        self.assertEqual(report.equal_timestamp_count, 1)
        self.assertEqual(report.duplicate_tick_count, 1)
        self.assertEqual(report.crossed_quote_count, 2)
        self.assertIn("OUT_OF_ORDER_TICKS", report.hard_failures)
        self.assertIn("CROSSED_QUOTES", report.hard_failures)

    def test_gap_and_missing_ratio_are_only_inferred_when_configured(self):
        ticks = [Tick(0, 1.1, 1.1001), Tick(400, 1.1, 1.1001)]
        report = TickFeedValidator(expected_interval_ms=100, gap_threshold_ms=250).validate(ticks)
        self.assertEqual(report.gap_count, 1)
        self.assertAlmostEqual(report.missing_tick_ratio, 3 / 5)


class ExecutableBacktesterTests(unittest.TestCase):
    def test_long_enters_ask_and_exits_on_bid_tp(self):
        ticks = [
            Tick(T0, 1.1000, 1.1001),
            Tick(T0 + 1000, 1.1031, 1.1032),
        ]
        result = ExecutableBidAskBacktester().simulate(long_candidate(), ticks)
        self.assertIs(result.outcome, BacktestOutcome.TAKE_PROFIT)
        self.assertEqual(result.label, 1)
        self.assertAlmostEqual(result.entry_price, 1.1001)
        self.assertAlmostEqual(result.exit_price, 1.1031)
        self.assertAlmostEqual(result.net_r, 3.0)
        self.assertAlmostEqual(result.gross_r - result.spread_cost_r - result.slippage_cost_r, result.net_r)

    def test_short_enters_bid_and_exits_on_ask_tp(self):
        ticks = [
            Tick(T0, 1.1000, 1.1001),
            Tick(T0 + 1000, 1.0969, 1.0970),
        ]
        result = ExecutableBidAskBacktester().simulate(short_candidate(), ticks)
        self.assertIs(result.outcome, BacktestOutcome.TAKE_PROFIT)
        self.assertAlmostEqual(result.entry_price, 1.1000)
        self.assertAlmostEqual(result.exit_price, 1.0970)
        self.assertAlmostEqual(result.net_r, 3.0)

    def test_adverse_slippage_is_explicit_and_not_double_counted(self):
        ticks = [
            Tick(T0, 1.1000, 1.1001),
            Tick(T0 + 1000, 1.1031, 1.1032),
        ]
        fills = FillAssumption(entry_slippage_pips=0.2, exit_slippage_pips=0.3)
        result = ExecutableBidAskBacktester(fills=fills).simulate(long_candidate(), ticks)
        self.assertAlmostEqual(result.slippage_cost_r, 0.05)
        self.assertAlmostEqual(result.net_r, 2.95)
        self.assertAlmostEqual(result.gross_r - result.spread_cost_r - result.slippage_cost_r, result.net_r)

    def test_same_timestamp_conflicting_barriers_are_ambiguous_and_conservative(self):
        ticks = [
            Tick(T0, 1.1000, 1.1001),
            Tick(T0 + 1000, 1.1031, 1.1032),
            Tick(T0 + 1000, 1.0990, 1.0991),
        ]
        result = ExecutableBidAskBacktester().simulate(long_candidate(), ticks)
        self.assertIs(result.outcome, BacktestOutcome.AMBIGUOUS)
        self.assertEqual(result.label, 0)
        self.assertAlmostEqual(result.exit_price, 1.0990)
        self.assertLess(result.net_r, 0)
        self.assertIn("CONFLICTING_BARRIERS_SAME_TIMESTAMP_CONSERVATIVE", result.notes)

    def test_vertical_barrier_uses_first_executable_tick_after_barrier(self):
        ticks = [
            Tick(T0, 1.1000, 1.1001),
            Tick(T0 + 4 * 60_000, 1.1004, 1.1005),
            Tick(T0 + 5 * 60_000 + 1, 1.1005, 1.1006),
        ]
        result = ExecutableBidAskBacktester().simulate(long_candidate(), ticks)
        self.assertIs(result.outcome, BacktestOutcome.VERTICAL)
        self.assertEqual(result.exit_time_msc, T0 + 5 * 60_000 + 1)

    def test_force_no_fill_is_deterministic(self):
        result = ExecutableBidAskBacktester(fills=FillAssumption(force_no_fill=True)).simulate(
            long_candidate(), [Tick(T0, 1.1000, 1.1001)]
        )
        self.assertIs(result.outcome, BacktestOutcome.NO_FILL)
        self.assertIsNone(result.net_r)

    def test_bad_feed_is_rejected_before_backtest(self):
        ticks = [Tick(T0 + 1, 1.1000, 1.1001), Tick(T0, 1.1000, 1.1001)]
        with self.assertRaisesRegex(DataQualityViolation, "OUT_OF_ORDER_TICKS"):
            ExecutableBidAskBacktester().simulate(long_candidate(), ticks)


class FakeMT5:
    COPY_TICKS_ALL = 7

    def __init__(self):
        self.initialized = False
        self.closed = False
        self.received = None

    def initialize(self):
        self.initialized = True
        return True

    def shutdown(self):
        self.closed = True

    def last_error(self):
        return (0, "ok")

    def copy_ticks_range(self, symbol, date_from, date_to, flags):
        self.received = (symbol, date_from, date_to, flags)
        return [{"time_msc": 1000, "bid": 1.1, "ask": 1.1001, "flags": 6}]


class RoutedMT5(FakeMT5):
    def __init__(self, rows_for_start):
        super().__init__()
        self.rows_for_start = rows_for_start
        self.calls = 0

    def copy_ticks_range(self, symbol, date_from, date_to, flags):
        self.received = (symbol, date_from, date_to, flags)
        self.calls += 1
        return self.rows_for_start(date_from)


class MT5AdapterTests(unittest.TestCase):
    def test_collector_uses_utc_and_preserves_tick_fields(self):
        api = FakeMT5()
        collector = MT5TickCollector(api=api)
        ticks = collector.collect(
            datetime(2026, 8, 5, 10, tzinfo=UTC),
            datetime(2026, 8, 5, 11, tzinfo=UTC),
        )
        self.assertTrue(api.initialized and api.closed)
        self.assertEqual(api.received[0], "EURUSD")
        self.assertEqual(api.received[3], api.COPY_TICKS_ALL)
        self.assertEqual(ticks[0].time_msc, 1000)
        self.assertEqual(ticks[0].flags, 6)

    def test_resumable_pipeline_writes_lineage_after_quality_gate(self):
        api = FakeMT5()
        with tempfile.TemporaryDirectory() as directory:
            pipeline = HistoricalTickPipeline(
                MT5TickCollector(api), directory, calendar_snapshot_id="calendar-v1",
                parquet_writer=lambda ticks, path: path.write_bytes(b"test-parquet") or path,
            )
            start, end = BASE, BASE + timedelta(hours=2)
            first = pipeline.collect(start, end, chunk=timedelta(hours=1))
            second = pipeline.collect(start, end, chunk=timedelta(hours=1))
            self.assertTrue(all(chunk.parquet_path.exists() and chunk.lineage_path.exists() for chunk in first))
            self.assertTrue(all(chunk.resumed for chunk in second))
            lineage = json.loads(first[0].lineage_path.read_text(encoding="utf-8"))
            self.assertEqual(lineage["calendar_snapshot_id"], "calendar-v1")

    def test_empty_saturday_is_a_lineage_only_expected_closure_and_resumes(self):
        api = RoutedMT5(lambda _: [])
        with tempfile.TemporaryDirectory() as directory:
            pipeline = HistoricalTickPipeline(MT5TickCollector(api), directory)
            start = datetime(2026, 7, 4, 0, tzinfo=UTC)
            first = pipeline.collect(start, start + timedelta(hours=12), chunk=timedelta(hours=12))
            second = pipeline.collect(start, start + timedelta(hours=12), chunk=timedelta(hours=12))
            self.assertEqual(first[0].status, "EXPECTED_MARKET_CLOSED")
            self.assertIsNone(first[0].parquet_path)
            self.assertTrue(first[0].lineage_path.exists())
            self.assertTrue(second[0].resumed)
            self.assertEqual(api.calls, 1)
            lineage = json.loads(first[0].lineage_path.read_text(encoding="utf-8"))
            self.assertEqual(lineage["status"], "EXPECTED_MARKET_CLOSED")
            self.assertIn("EMPTY_FEED", lineage["quality"]["hard_failures"])

    def test_empty_sunday_is_an_expected_closure(self):
        api = RoutedMT5(lambda _: [])
        with tempfile.TemporaryDirectory() as directory:
            result = HistoricalTickPipeline(MT5TickCollector(api), directory).collect(
                datetime(2026, 7, 5, 6, tzinfo=UTC), datetime(2026, 7, 5, 18, tzinfo=UTC),
                chunk=timedelta(hours=12),
            )
            self.assertEqual(result[0].status, "EXPECTED_MARKET_CLOSED")
            self.assertIsNone(result[0].parquet_path)

    def test_empty_weekday_still_hard_fails(self):
        api = RoutedMT5(lambda _: [])
        with tempfile.TemporaryDirectory() as directory:
            pipeline = HistoricalTickPipeline(MT5TickCollector(api), directory)
            with self.assertRaisesRegex(DataQualityViolation, "EMPTY_FEED"):
                pipeline.collect(datetime(2026, 7, 6, 0, tzinfo=UTC), datetime(2026, 7, 6, 1, tzinfo=UTC))

    def test_nonempty_weekend_chunk_preserves_actual_ticks(self):
        rows = [{"time_msc": 1_000, "bid": 1.1, "ask": 1.1001, "flags": 6}]
        api = RoutedMT5(lambda _: rows)
        with tempfile.TemporaryDirectory() as directory:
            result = HistoricalTickPipeline(
                MT5TickCollector(api), directory,
                parquet_writer=lambda ticks, path: path.write_bytes(b"actual-ticks") or path,
            ).collect(datetime(2026, 7, 4, 2, tzinfo=UTC), datetime(2026, 7, 4, 3, tzinfo=UTC))
            self.assertEqual(result[0].status, "COMPLETED")
            self.assertTrue(result[0].parquet_path.exists())
            self.assertEqual(result[0].parquet_path.read_bytes(), b"actual-ticks")

    def test_empty_interval_overlapping_trading_time_is_not_suppressed(self):
        api = RoutedMT5(lambda _: [])
        with tempfile.TemporaryDirectory() as directory:
            pipeline = HistoricalTickPipeline(MT5TickCollector(api), directory)
            with self.assertRaisesRegex(DataQualityViolation, "EMPTY_FEED"):
                pipeline.collect(datetime(2026, 7, 3, 23, tzinfo=UTC), datetime(2026, 7, 4, 1, tzinfo=UTC))


class TemporalHazardTests(unittest.TestCase):
    def test_london_open_is_dst_aware_not_hardcoded_utc(self):
        clock = MarketClock()
        registry = BenchmarkWindowRegistry(half_width_minutes=0)
        winter = clock.from_utc(datetime(2026, 1, 15, 8, 0, tzinfo=UTC))
        summer = clock.from_utc(datetime(2026, 7, 15, 7, 0, tzinfo=UTC))
        self.assertTrue(registry.classify(winter).london_open)
        self.assertTrue(registry.classify(summer).london_open)
        self.assertEqual(winter.london.hour, 8)
        self.assertEqual(summer.london.hour, 8)

    def test_eu_us_dst_mismatch_week_is_explicit(self):
        state = MarketClock().from_utc(datetime(2026, 3, 15, 12, 0, tzinfo=UTC))
        self.assertEqual(state.dst_state, "US_DST_EU_STANDARD")

    def test_high_impact_release_hard_vetoes_without_changing_direction(self):
        event_time = BASE + timedelta(minutes=10)
        snapshot = CalendarSnapshot(
            snapshot_id="official-2026-08-05-v1",
            as_of=BASE - timedelta(hours=1),
            source="TEST_OFFICIAL_SNAPSHOT",
            events=(
                MacroEvent(
                    event_id="us-cpi-20260805",
                    event_code="US_CPI_RELEASE_WINDOW",
                    name="US CPI",
                    currency="USD",
                    scheduled_at=event_time,
                    impact=Impact.HIGH,
                    source="TEST_OFFICIAL_SNAPSHOT",
                ),
            ),
        )
        candidate = long_candidate(entry_available_at=event_time + timedelta(minutes=2))
        output = ScheduledMacroJumpGuard().evaluate(candidate, EconomicCalendarAdapter(snapshot))
        self.assertIs(output.decision_effect, DecisionEffect.HARD_VETO)
        self.assertFalse(output.valid)
        self.assertEqual(output.signal, -1.0)
        self.assertTrue(output.candidate_direction_unchanged)
        self.assertEqual(output.features["seconds_from_release"], 120.0)
        self.assertIn(snapshot.snapshot_id, output.lineage_ids)

    def test_medium_impact_event_does_not_trigger_scheduled_hard_veto(self):
        snapshot = CalendarSnapshot(
            snapshot_id="calendar-v1",
            as_of=BASE - timedelta(hours=1),
            source="TEST",
            events=(
                MacroEvent("e1", "MEDIUM_EVENT", "Medium", "EUR", BASE, Impact.MEDIUM, "TEST"),
            ),
        )
        output = ScheduledMacroJumpGuard().evaluate(long_candidate(), EconomicCalendarAdapter(snapshot))
        self.assertIs(output.decision_effect, DecisionEffect.NEUTRAL)
        self.assertTrue(output.valid)

    def test_future_high_impact_event_outside_pre_window_is_neutral(self):
        snapshot = CalendarSnapshot(
            snapshot_id="calendar-v2",
            as_of=BASE - timedelta(hours=1),
            source="TEST",
            events=(
                MacroEvent(
                    "e2",
                    "US_HIGH_EVENT",
                    "High event later",
                    "USD",
                    BASE + timedelta(minutes=10),
                    Impact.HIGH,
                    "TEST",
                ),
            ),
        )
        output = ScheduledMacroJumpGuard().evaluate(long_candidate(), EconomicCalendarAdapter(snapshot))
        self.assertIs(output.decision_effect, DecisionEffect.NEUTRAL)

    def test_future_calendar_snapshot_is_rejected_as_leakage(self):
        snapshot = CalendarSnapshot(
            snapshot_id="revised-after-event",
            as_of=BASE + timedelta(hours=1),
            source="TEST",
            events=(),
        )
        with self.assertRaises(CalendarLeakageError):
            ScheduledMacroJumpGuard().evaluate(long_candidate(), EconomicCalendarAdapter(snapshot))

    def test_json_snapshot_loader_rejects_revised_fields_and_preserves_as_of(self):
        payload = {"snapshot_id": "official-v1", "as_of": "2026-08-05T09:00:00Z", "source": "OFFICIAL",
                   "events": [{"event_id": "e1", "event_code": "US_CPI", "name": "CPI", "currency": "USD",
                               "scheduled_at": "2026-08-05T10:00:00Z", "impact": "HIGH"}]}
        with tempfile.TemporaryDirectory() as directory:
            calendar_path = Path(directory) / "calendar.json"
            calendar_path.write_text(json.dumps(payload), encoding="utf-8")
            snapshot = load_calendar_snapshot(calendar_path)
        self.assertEqual(snapshot.snapshot_id, "official-v1")
        self.assertEqual(snapshot.events[0].scheduled_at, BASE)
        payload["revised_value"] = 7
        with tempfile.TemporaryDirectory() as directory:
            calendar_path = Path(directory) / "calendar.json"
            calendar_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(CalendarSnapshotValidationError):
                load_calendar_snapshot(calendar_path)

    def test_post_jump_inputs_are_bounded_by_explicit_observation_cutoff(self):
        event = MacroEvent("e1", "US_CPI", "CPI", "USD", BASE, Impact.HIGH, "TEST")
        inputs = post_jump_stabilisation_inputs(event, [
            Tick(T0, 1.1, 1.1001), Tick(T0 + 1000, 1.1002, 1.1004), Tick(T0 + 5000, 1.2, 1.2001),
        ], observation_end_msc=T0 + 1000)
        self.assertEqual(inputs.tick_count, 2)
        self.assertEqual(inputs.status, "RESEARCH")


if __name__ == "__main__":
    unittest.main()
