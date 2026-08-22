"""Synthetic regression coverage for the read-only Gen-3 lineage audit."""

import json
import tempfile
import unittest
from pathlib import Path

from engine.gen3.lineage import audit_lineage, write_audit


class Gen3LineageAuditTests(unittest.TestCase):
    def put(self, root, name, start, end, status="EXPECTED_MARKET_CLOSED", tick_count=0, filename=None, **extra):
        record = {"lineage_id": name, "start": start, "end": end, "status": status, "tick_count": tick_count}
        record.update(extra)
        Path(root, f"{filename or name}.lineage.json").write_text(json.dumps(record), encoding="utf-8")

    def assert_fails(self, root, expected):
        report = audit_lineage(root)
        self.assertEqual("FAIL", report["audit_status"])
        self.assertTrue(any(expected in error for error in report["errors"]), report["errors"])

    def test_adjacent_metadata_is_deterministic_and_writer_is_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "a", "2024-08-01T00:00:00Z", "2024-08-02T00:00:00Z")
            self.put(root, "b", "2024-08-02T00:00:00Z", "2024-08-03T00:00:00Z", "NO_BROKER_HISTORY")
            first, second = audit_lineage(root), audit_lineage(root)
            self.assertEqual("PASS", first["audit_status"])
            self.assertEqual([], first["missing_history_intervals"])
            self.assertEqual(first["dataset_fingerprint"], second["dataset_fingerprint"])
            self.assertEqual({"EXPECTED_MARKET_CLOSED": 1, "NO_BROKER_HISTORY": 1}, first["chunk_counts_by_status"])
            output = write_audit(first, Path(root, "reports", "audit.json"))
            self.assertTrue(output.is_file())

    def test_detects_interval_and_identifier_contradictions(self):
        cases = [
            ([("a", "2024-08-01T00:00:00Z", "2024-08-03T00:00:00Z"), ("b", "2024-08-02T00:00:00Z", "2024-08-04T00:00:00Z")], "overlapping intervals"),
            ([("same", "2024-08-01T00:00:00Z", "2024-08-02T00:00:00Z"), ("same", "2024-08-02T00:00:00Z", "2024-08-03T00:00:00Z")], "duplicate lineage_id"),
            ([("a", "2024-08-01T00:00:00Z", "2024-08-02T00:00:00Z"), ("b", "2024-08-01T00:00:00Z", "2024-08-02T00:00:00Z")], "duplicate interval"),
        ]
        for rows, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as root:
                for index, (name, start, end) in enumerate(rows):
                    self.put(root, name, start, end, filename=f"sidecar-{index}")
                self.assert_fails(root, expected)

    def test_detects_missing_history_and_invalid_sidecars(self):
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "a", "2024-08-01T00:00:00Z", "2024-08-02T00:00:00Z")
            self.put(root, "b", "2024-08-03T00:00:00Z", "2024-08-04T00:00:00Z")
            report = audit_lineage(root)
            self.assertEqual("PASS", report["audit_status"])
            self.assertEqual([{"start": "2024-08-02T00:00:00Z", "end": "2024-08-03T00:00:00Z"}], report["missing_history_intervals"])
        invalid = [
            ({"start": "2024-08-01T00:00:00", "end": "2024-08-02T00:00:00Z", "status": "EXPECTED_MARKET_CLOSED", "tick_count": 0}, "UTC-aware"),
            ({"start": "2024-08-02T00:00:00Z", "end": "2024-08-01T00:00:00Z", "status": "EXPECTED_MARKET_CLOSED", "tick_count": 0}, "non-positive"),
            ({"start": "2024-08-01T00:00:00Z", "end": "2024-08-02T00:00:00Z", "status": "UNKNOWN", "tick_count": 0}, "unknown status"),
            ({"start": "2024-08-01T00:00:00Z", "end": "2024-08-02T00:00:00Z", "status": "EXPECTED_MARKET_CLOSED", "tick_count": -1}, "invalid tick_count"),
        ]
        for record, expected in invalid:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as root:
                Path(root, "bad.lineage.json").write_text(json.dumps(record), encoding="utf-8")
                self.assert_fails(root, expected)

    def test_completed_parquet_requirements_and_hash_contract(self):
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "missing", "2024-08-01T00:00:00Z", "2024-08-02T00:00:00Z", "COMPLETED", 1)
            self.assert_fails(root, "COMPLETED interval has no Parquet")
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "closed", "2024-08-01T00:00:00Z", "2024-08-02T00:00:00Z")
            Path(root, "closed.parquet").write_bytes(b"not parquet")
            self.assert_fails(root, "non-COMPLETED interval has a Parquet")
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "bad-hash", "2024-08-01T00:00:00Z", "2024-08-02T00:00:00Z", source_hash="not-a-hash")
            self.assert_fails(root, "declared file hash")

    def test_completed_parquet_footer_count_and_schema_are_verified(self):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:  # pragma: no cover - project test environments provide pyarrow
            self.skipTest("pyarrow unavailable")
        fields = {
            "time_msc": pa.array([1]), "timestamp_utc": pa.array(["2024-08-01T00:00:00Z"]),
            "bid": pa.array([1.1]), "ask": pa.array([1.2]), "flags": pa.array([0]),
        }
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "good", "2024-08-01T00:00:00Z", "2024-08-02T00:00:00Z", "COMPLETED", 1)
            pq.write_table(pa.table(fields), Path(root, "good.parquet"))
            self.assertEqual("PASS", audit_lineage(root)["audit_status"])
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "wrong-count", "2024-08-01T00:00:00Z", "2024-08-02T00:00:00Z", "COMPLETED", 2)
            pq.write_table(pa.table(fields), Path(root, "wrong-count.parquet"))
            self.assert_fails(root, "footer row count")
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "wrong-schema", "2024-08-01T00:00:00Z", "2024-08-02T00:00:00Z", "COMPLETED", 1)
            pq.write_table(pa.table({"time_msc": pa.array([1])}), Path(root, "wrong-schema.parquet"))
            self.assert_fails(root, "schema missing columns")

    def test_legacy_completed_sidecar_requires_valid_quality_and_parquet(self):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:  # pragma: no cover
            self.skipTest("pyarrow unavailable")
        fields = {name: pa.array([0]) for name in ("time_msc", "timestamp_utc", "bid", "ask", "flags")}
        with tempfile.TemporaryDirectory() as root:
            self.put(root, "legacy", "2024-08-01T00:00:00Z", "2024-08-02T00:00:00Z", tick_count=1, quality={"valid": True})
            payload = json.loads(Path(root, "legacy.lineage.json").read_text(encoding="utf-8"))
            payload.pop("status")
            Path(root, "legacy.lineage.json").write_text(json.dumps(payload), encoding="utf-8")
            pq.write_table(pa.table(fields), Path(root, "legacy.parquet"))
            report = audit_lineage(root)
            self.assertEqual("PASS", report["audit_status"])
            self.assertEqual({"COMPLETED": 1}, report["chunk_counts_by_status"])
            self.assertEqual(1, len(report["warnings"]))

    def test_monthly_bar_partition_coverage_and_data_root_discovery(self):
        with tempfile.TemporaryDirectory() as root:
            raw = Path(root, "processed", "mt5")
            raw.mkdir(parents=True)
            self.put(raw, "a", "2024-08-01T00:00:00Z", "2024-08-02T00:00:00Z")
            bars = Path(root, "processed", "bars", "EURUSD")
            for timeframe in ("M5", "M15", "H1"):
                directory = bars / timeframe
                directory.mkdir(parents=True)
                Path(directory, f"EURUSD_{timeframe}_202408.parquet").write_bytes(b"")
            report = audit_lineage(root)
            self.assertEqual("PASS", report["audit_status"])
            self.assertEqual({"M5": True, "M15": True, "H1": True}, report["bar_partition_coverage"]["2024-08"])
            (bars / "H1" / "EURUSD_H1_202408.parquet").unlink()
            self.assert_fails(root, "missing bar partitions for 2024-08: H1")

    def test_multi_month_interval_uses_half_open_utc_month_coverage(self):
        with tempfile.TemporaryDirectory() as root:
            bars = Path(root, "bars")
            self.put(root, "month-boundary", "2024-08-31T23:00:00Z", "2024-09-01T01:00:00Z")
            for month in ("202408", "202409"):
                for timeframe in ("M5", "M15", "H1"):
                    directory = bars / timeframe
                    directory.mkdir(parents=True, exist_ok=True)
                    Path(directory, f"EURUSD_{timeframe}_{month}.parquet").write_bytes(b"")
            self.assertEqual("PASS", audit_lineage(root, bars)["audit_status"])
            (bars / "M5" / "EURUSD_M5_202409.parquet").unlink()
            self.assert_fails_with_bars(root, bars, "missing bar partitions for 2024-09: M5")

    def assert_fails_with_bars(self, root, bars, expected):
        report = audit_lineage(root, bars)
        self.assertEqual("FAIL", report["audit_status"])
        self.assertTrue(any(expected in error for error in report["errors"]), report["errors"])


if __name__ == "__main__":
    unittest.main()
