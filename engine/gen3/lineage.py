"""Read-only, deterministic audit of MT5 lineage sidecars and Parquet footers.

The audit intentionally never loads tick columns.  It validates only sidecar JSON,
file presence, and Parquet footer metadata, so it is safe to run against local
broker-derived history without creating, moving, or modifying market data.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


AUDIT_SCHEMA_VERSION = "gen3-lineage-audit/v1"
SUPPORTED_SIDECAR_VERSIONS = {None, "mt5-lineage/v1"}
VALID_STATUSES = {"COMPLETED", "EXPECTED_MARKET_CLOSED", "NO_BROKER_HISTORY"}
REQUIRED_TICK_COLUMNS = {"time_msc", "timestamp_utc", "bid", "ask", "flags"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("timestamp must be UTC-aware")
    return parsed


def _timestamp_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _resolve_roots(data_dir: str | Path, bars_dir: str | Path | None) -> tuple[Path, Path | None]:
    requested = Path(data_dir)
    sidecars = requested / "processed" / "mt5"
    raw_dir = sidecars if sidecars.is_dir() else requested
    if bars_dir is not None:
        return raw_dir, Path(bars_dir)
    inferred = requested / "processed" / "bars" / "EURUSD"
    return raw_dir, inferred if inferred.is_dir() else None


def _parquet_footer(path: Path) -> tuple[int, list[str]]:
    try:
        import pyarrow.parquet as parquet
    except ImportError as error:  # pragma: no cover - environment failure, not a data result
        raise RuntimeError("pyarrow is required for Parquet-footer validation") from error
    try:
        metadata = parquet.ParquetFile(path).metadata
    except Exception as error:  # pyarrow uses implementation-specific exception types
        raise ValueError("invalid Parquet footer") from error
    return metadata.num_rows, list(metadata.schema.names)


def _declared_hash(record: dict[str, Any]) -> str | None:
    hashes = [record[key] for key in ("source_hash", "file_hash") if key in record]
    if len(hashes) > 1 and len(set(hashes)) != 1:
        raise ValueError("conflicting declared file hashes")
    value = hashes[0] if hashes else None
    if value is not None and (not isinstance(value, str) or not _SHA256.fullmatch(value)):
        raise ValueError("declared file hash must be a lowercase SHA-256")
    return value


def _status_from_sidecar(record: dict[str, Any], parquet_exists: bool) -> tuple[str, bool]:
    """Normalize the current explicit schema and a documented legacy completed form."""
    if "status" in record:
        status = record["status"]
        if status not in VALID_STATUSES:
            raise ValueError("unknown status")
        return status, False
    # Older writer versions emitted a successful quality block and its Parquet
    # file but did not serialize the redundant top-level COMPLETED status.
    if parquet_exists and isinstance(record.get("quality"), dict) and record["quality"].get("valid") is True:
        return "COMPLETED", True
    raise ValueError("missing status")


def _bar_partition_coverage(bars_dir: Path | None, months: list[str]) -> dict[str, dict[str, bool]]:
    if bars_dir is None:
        return {}
    result: dict[str, dict[str, bool]] = {}
    for month in months:
        compact = month.replace("-", "")
        result[month] = {
            timeframe: any((bars_dir / timeframe).glob(f"*{compact}*.parquet"))
            for timeframe in ("M5", "M15", "H1")
        }
    return result


def _months_touched(start: str, end: str) -> set[str]:
    """Return UTC calendar months intersecting the half-open [start, end) interval."""
    cursor = _utc_timestamp(start).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    final = _utc_timestamp(end) - timedelta(microseconds=1)
    months: set[str] = set()
    while cursor <= final:
        months.add(cursor.strftime("%Y-%m"))
        cursor = cursor.replace(year=cursor.year + 1, month=1) if cursor.month == 12 else cursor.replace(month=cursor.month + 1)
    return months


def audit_lineage(data_dir: str | Path, bars_dir: str | Path | None = None) -> dict[str, Any]:
    """Audit local lineage without scanning tick data or writing any artifacts."""
    raw_dir, resolved_bars_dir = _resolve_roots(data_dir, bars_dir)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    sidecar_paths: list[str] = []

    for sidecar in sorted(raw_dir.glob("*.lineage.json")):
        sidecar_paths.append(str(sidecar))
        try:
            record = json.loads(sidecar.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError("sidecar must be a JSON object")
            start, end = _utc_timestamp(record["start"]), _utc_timestamp(record["end"])
            tick_count = record["tick_count"]
            identifier = record.get("lineage_id", sidecar.name.removesuffix(".lineage.json"))
            if end <= start:
                raise ValueError("non-positive interval")
            if not isinstance(identifier, str) or not identifier:
                raise ValueError("invalid lineage_id")
            if type(tick_count) is not int or tick_count < 0:
                raise ValueError("invalid tick_count")
            if record.get("schema_version") not in SUPPORTED_SIDECAR_VERSIONS:
                raise ValueError("unsupported sidecar schema")
            declared_hash = _declared_hash(record)
            parquet_path = sidecar.with_name(sidecar.name.removesuffix(".lineage.json") + ".parquet")
            parquet_exists = parquet_path.is_file()
            status, inferred_legacy_status = _status_from_sidecar(record, parquet_exists)
            if inferred_legacy_status:
                warnings.append(f"{sidecar.name}: inferred legacy COMPLETED status from valid quality and Parquet")
            if status == "COMPLETED" and not parquet_exists:
                raise ValueError("COMPLETED interval has no Parquet file")
            if status != "COMPLETED" and parquet_exists:
                raise ValueError("non-COMPLETED interval has a Parquet file")
            if parquet_exists:
                footer_rows, columns = _parquet_footer(parquet_path)
                if footer_rows != tick_count:
                    raise ValueError("Parquet footer row count differs from sidecar tick_count")
                missing_columns = sorted(REQUIRED_TICK_COLUMNS.difference(columns))
                if missing_columns:
                    raise ValueError(f"Parquet schema missing columns: {','.join(missing_columns)}")
            rows.append(
                {
                    "id": identifier,
                    "start": _timestamp_text(start),
                    "end": _timestamp_text(end),
                    "status": status,
                    "tick_count": tick_count,
                    "parquet_file": parquet_path.name if parquet_exists else None,
                    "declared_file_hash": declared_hash,
                }
            )
        except (KeyError, TypeError, ValueError, OSError, RuntimeError) as error:
            errors.append(f"{sidecar.name}: {error}")

    rows.sort(key=lambda row: (row["start"], row["end"], row["id"]))
    if len({row["id"] for row in rows}) != len(rows):
        errors.append("duplicate lineage_id")
    if len({(row["start"], row["end"]) for row in rows}) != len(rows):
        errors.append("duplicate interval")

    missing_intervals: list[dict[str, str]] = []
    for previous, current in zip(rows, rows[1:]):
        if previous["end"] > current["start"]:
            errors.append("overlapping intervals")
        elif previous["end"] < current["start"]:
            missing_intervals.append({"start": previous["end"], "end": current["start"]})

    month_counts = Counter(row["start"][:7] for row in rows)
    months = sorted({month for row in rows for month in _months_touched(row["start"], row["end"])})
    partitions = _bar_partition_coverage(resolved_bars_dir, months)
    for month, present in partitions.items():
        absent = [timeframe for timeframe, exists in present.items() if not exists]
        if absent:
            errors.append(f"missing bar partitions for {month}: {','.join(absent)}")

    projection = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "chunks": rows,
        "missing_history_intervals": missing_intervals,
        "bar_partition_coverage": partitions,
    }
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "created_at_utc": _timestamp_text(datetime.now(UTC)),
        "audit_status": "FAIL" if errors else "PASS",
        "dataset_fingerprint": _canonical_hash(projection),
        "source_manifest_paths": sidecar_paths,
        "chunk_counts_by_status": dict(sorted(Counter(row["status"] for row in rows).items())),
        "total_declared_ticks": sum(row["tick_count"] for row in rows),
        "coverage_start": rows[0]["start"] if rows else None,
        "coverage_end": rows[-1]["end"] if rows else None,
        "coverage_by_month": {month: month_counts[month] for month in months},
        "missing_history_intervals": missing_intervals,
        "bar_partition_coverage": partitions,
        "warnings": sorted(warnings),
        "errors": sorted(set(errors)),
        "limitations": [
            "Read-only sidecar and Parquet-footer inspection only; tick rows are not scanned.",
            "Declared source/file hashes are format-validated but cannot be recomputed without a full file scan.",
        ],
    }


def write_audit(result: dict[str, Any], output_path: str | Path) -> Path:
    """Explicitly write a deterministic audit report; auditing itself never writes."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return output
