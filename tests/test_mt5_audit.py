import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from demo_beta.data.mt5_audit import MT5AuditConfig, MT5HistoryAuditor


def _ticks(moment: datetime, offsets=(0, 1000), *, ask_offset=0.0001):
    base = int(moment.timestamp() * 1000)
    return [(base + offset, 1.1000, 1.1000 + ask_offset, 6) for offset in offsets]


class MT5HistoryAuditTests(unittest.TestCase):
    def _write_chunk(self, directory: str, start: datetime, end: datetime, ticks, *, lineage_count=None, status="COMPLETED"):
        name = f"EURUSD_{start:%Y%m%dT%H%M%SZ}_{end:%Y%m%dT%H%M%SZ}"
        path = Path(directory)
        parquet = path / f"{name}.parquet"
        if ticks is not None:
            pq.write_table(pa.table({"time_msc": [x[0] for x in ticks], "bid": [x[1] for x in ticks],
                                     "ask": [x[2] for x in ticks], "flags": [x[3] for x in ticks]}), parquet)
        lineage = {"pair": "EUR_USD", "source": "MT5_COPY_TICKS_ALL",
                   "start": start.isoformat().replace("+00:00", "Z"), "end": end.isoformat().replace("+00:00", "Z"),
                   "tick_count": len(ticks or []) if lineage_count is None else lineage_count, "status": status}
        (path / f"{name}.lineage.json").write_text(json.dumps(lineage), encoding="utf-8")

    def _audit(self, directory, start, end):
        return MT5HistoryAuditor(directory).audit(start, end)

    def test_complete_healthy_period_is_pass_and_deterministic(self):
        start = datetime(2026, 7, 6, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            self._write_chunk(directory, start, start + timedelta(days=1), _ticks(start))
            first = self._audit(directory, start, start + timedelta(days=1))
            second = self._audit(directory, start, start + timedelta(days=1))
            self.assertEqual(first, second)
            self.assertEqual(first["severity"], "PASS")
            self.assertEqual(first["coverage"]["percentage"], 100.0)

    def test_half_open_month_has_31_calendar_days_not_32(self):
        start = datetime(2026, 7, 1, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            current = start
            while current < datetime(2026, 8, 1, tzinfo=UTC):
                end = current + timedelta(days=1)
                if current.weekday() in (5, 6):
                    self._write_chunk(directory, current, end, None, status="EXPECTED_MARKET_CLOSED")
                else:
                    self._write_chunk(directory, current, end, _ticks(current))
                current = end
            report = self._audit(directory, start, current)
            self.assertEqual(report["coverage"]["calendar_days"], 31)

    def test_expected_weekend_closure_is_covered_without_parquet(self):
        start = datetime(2026, 7, 4, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            self._write_chunk(directory, start, start + timedelta(days=1), None, status="EXPECTED_MARKET_CLOSED")
            report = self._audit(directory, start, start + timedelta(days=1))
            self.assertEqual(report["severity"], "PASS")
            self.assertEqual(report["coverage"]["expected_market_closed_chunks"], 1)

    def test_missing_weekday_file_fails(self):
        start = datetime(2026, 7, 6, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            report = self._audit(directory, start, start + timedelta(days=1))
            self.assertEqual(report["severity"], "FAIL")
            self.assertIn("MISSING_EXPECTED_CHUNK", report["failures"])

    def test_lineage_row_count_mismatch_fails(self):
        start = datetime(2026, 7, 6, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            self._write_chunk(directory, start, start + timedelta(days=1), _ticks(start), lineage_count=99)
            report = self._audit(directory, start, start + timedelta(days=1))
            self.assertIn("LINEAGE_MISMATCH", report["failures"])

    def test_duplicates_and_equal_timestamps_are_reported(self):
        start = datetime(2026, 7, 6, tzinfo=UTC)
        rows = _ticks(start, (0, 0, 1000))
        with tempfile.TemporaryDirectory() as directory:
            self._write_chunk(directory, start, start + timedelta(days=1), rows)
            report = self._audit(directory, start, start + timedelta(days=1))
            self.assertEqual(report["severity"], "WARN")
            self.assertEqual(report["quality"]["duplicate_tick_count"], 1)
            self.assertEqual(report["quality"]["equal_timestamp_count"], 1)

    def test_crossed_and_out_of_order_ticks_fail(self):
        start = datetime(2026, 7, 6, tzinfo=UTC)
        rows = [(int(start.timestamp() * 1000) + 1000, 1.1001, 1.1000, 6),
                (int(start.timestamp() * 1000), 1.1000, 1.1001, 6)]
        with tempfile.TemporaryDirectory() as directory:
            self._write_chunk(directory, start, start + timedelta(days=1), rows)
            report = self._audit(directory, start, start + timedelta(days=1))
            self.assertIn("CROSSED_QUOTES", report["failures"])
            self.assertIn("OUT_OF_ORDER_TICKS", report["failures"])

    def test_zero_and_extreme_spreads_are_visible_without_removal(self):
        start = datetime(2026, 7, 6, tzinfo=UTC)
        base = int(start.timestamp() * 1000)
        rows = [(base, 1.1000, 1.1000, 6), (base + 1000, 1.1000, 1.1010, 6)]
        with tempfile.TemporaryDirectory() as directory:
            self._write_chunk(directory, start, start + timedelta(days=1), rows)
            report = self._audit(directory, start, start + timedelta(days=1))
            self.assertEqual(report["quality"]["zero_spread_ratio"], .5)
            self.assertEqual(report["quality"]["zero_spread_count"], 1)
            self.assertEqual(report["quality"]["zero_spread_by_utc_day"]["2026-07-06"]["count"], 1)
            self.assertEqual(report["quality"]["zero_spread_by_utc_hour"]["0"]["ratio"], .5)
            self.assertEqual(report["quality"]["extreme_spread_count"], 1)
            self.assertAlmostEqual(report["quality"]["extreme_spread_observations"][0]["spread_pips"], 10.0)
            self.assertEqual(report["quality"]["extreme_spread_by_utc_hour"]["0"], 1)
            self.assertEqual(report["quality"]["extreme_spread_most_affected_utc_hour"], 0)
            self.assertEqual(report["quality"]["extreme_spread_percentage_in_most_affected_hour"], 100.0)

    def test_intraday_gap_warns_but_weekend_gap_does_not(self):
        monday = datetime(2026, 7, 6, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            self._write_chunk(directory, monday, monday + timedelta(days=1), _ticks(monday, (0, 61_000)))
            report = self._audit(directory, monday, monday + timedelta(days=1))
            self.assertEqual(report["quality"]["suspicious_trading_gaps"], 1)
            gap = report["quality"]["suspicious_gap_observations"][0]
            self.assertEqual(gap["previous_tick_timestamp"], "2026-07-06T00:00:00Z")
            self.assertEqual(gap["next_tick_timestamp"], "2026-07-06T00:01:01Z")
            self.assertEqual(gap["gap_duration_ms"], 61_000)
            self.assertEqual(gap["gap_duration_seconds"], 61.0)
            self.assertEqual(gap["utc_date"], "2026-07-06")
            self.assertEqual(gap["utc_hour"], 0)
            self.assertFalse(gap["touches_expected_market_closure"])
            self.assertEqual(gap["previous_bid"], 1.1)
            self.assertEqual(gap["next_ask"], 1.1001)
        saturday = datetime(2026, 7, 4, tzinfo=UTC)
        # The gap classifier itself suppresses a complete UTC Saturday/Sunday interval.
        quality = MT5HistoryAuditor(".")._quality(_ticks(saturday, (0, 120_000)))
        self.assertEqual(quality["suspicious_trading_gaps"], 0)

    def test_friday_to_monday_gaps_are_expected_closure_observations_not_suspicious(self):
        results = []
        for friday in (datetime(2026, 7, 3, 23, 59, 50, tzinfo=UTC),
                       datetime(2026, 7, 10, 23, 59, 50, tzinfo=UTC),
                       datetime(2026, 7, 17, 23, 59, 50, tzinfo=UTC),
                       datetime(2026, 7, 24, 23, 59, 50, tzinfo=UTC)):
            results.append(MT5HistoryAuditor(".")._quality(
                _ticks(friday, (0,)) + _ticks(friday + timedelta(days=2, seconds=10), (0,))
            ))
        self.assertEqual(sum(result["expected_market_closure_gaps"] for result in results), 4)
        self.assertEqual(sum(result["suspicious_trading_gaps"] for result in results), 0)
        observations = [gap for result in results for gap in result["expected_market_closure_gap_observations"]]
        self.assertEqual(len(observations), 4)
        self.assertTrue(all(
            gap["touches_expected_market_closure"]
            for gap in observations
        ))
