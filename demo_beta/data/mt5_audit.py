"""Read-only, deterministic quality audits for collected MT5 tick history.

The audit deliberately reports every observation it sees.  It neither repairs
nor filters raw ticks, so its JSON output is suitable as a lineage companion
before bars or backtests are constructed.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from ..contracts import jsonable


SCHEMA_VERSION = "mt5-history-audit/v1"
EXPECTED_SOURCE = "MT5_COPY_TICKS_ALL"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("audit bounds must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000.0, tz=UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] * (high - position) + values[high] * (position - low)


def _spread_summary(values: list[float]) -> dict[str, float | None]:
    return {"min": min(values) if values else None, "p25": _percentile(values, .25),
            "p50": _percentile(values, .50), "p75": _percentile(values, .75),
            "p95": _percentile(values, .95), "p99": _percentile(values, .99),
            "max": max(values) if values else None}


def _expected_weekend_closure(start: datetime, end: datetime) -> bool:
    """True only when the entire half-open UTC interval is Saturday/Sunday."""
    start, end = _utc(start), _utc(end)
    if start.weekday() not in (5, 6):
        return False
    monday = datetime(start.year, start.month, start.day, tzinfo=UTC) + timedelta(days=7 - start.weekday())
    return end <= monday


def _touches_expected_weekend_closure(start: datetime, end: datetime) -> bool:
    """Whether a UTC half-open interval overlaps any Saturday/Sunday closure."""
    start, end = _utc(start), _utc(end)
    day = datetime(start.year, start.month, start.day, tzinfo=UTC)
    while day < end:
        if day.weekday() in (5, 6):
            return True
        day += timedelta(days=1)
    return False


@dataclass(frozen=True, slots=True)
class MT5AuditConfig:
    """Visible review thresholds; none affects or removes source data."""
    pip_size: float = 0.0001
    suspicious_gap_ms: int = 60_000
    extreme_spread_pips: float = 5.0
    low_density_fraction_of_median: float = 0.20

    def __post_init__(self) -> None:
        if self.pip_size <= 0 or self.suspicious_gap_ms <= 0 or self.extreme_spread_pips <= 0:
            raise ValueError("audit pip size and thresholds must be positive")
        if not 0 < self.low_density_fraction_of_median <= 1:
            raise ValueError("low density fraction must be in (0, 1]")


class MT5HistoryAuditor:
    """Audit a deterministic range of existing MT5 Parquet/lineage chunks."""

    def __init__(self, input_dir: str | Path, *, symbol: str = "EURUSD", config: MT5AuditConfig | None = None) -> None:
        self.input_dir = Path(input_dir)
        self.symbol = symbol
        self.pair = "EUR_USD" if symbol.upper() == "EURUSD" else symbol
        self.config = config or MT5AuditConfig()

    def _paths(self, start: datetime, end: datetime) -> tuple[Path, Path]:
        name = f"{self.symbol}_{start:%Y%m%dT%H%M%SZ}_{end:%Y%m%dT%H%M%SZ}"
        return self.input_dir / f"{name}.parquet", self.input_dir / f"{name}.lineage.json"

    @staticmethod
    def _read_lineage(path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _lineage_time(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        try:
            return _iso(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None

    def _read_parquet(self, path: Path) -> tuple[int, list[tuple[int, float, float, int]]]:
        try:
            import pyarrow.parquet as pq  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("MT5 history audit requires pyarrow; install requirements.txt") from exc
        table = pq.read_table(path, columns=["time_msc", "bid", "ask", "flags"])
        names = set(table.column_names)
        required = {"time_msc", "bid", "ask", "flags"}
        if names != required:
            raise ValueError(f"unexpected Parquet schema in {path.name}: required {sorted(required)}")
        columns = [table.column(name).to_pylist() for name in ("time_msc", "bid", "ask", "flags")]
        return table.num_rows, list(zip(*columns))

    def audit(self, start: datetime, end: datetime, *, chunk: timedelta = timedelta(days=1)) -> dict[str, Any]:
        start, end = _utc(start), _utc(end)
        if end <= start or chunk <= timedelta(0):
            raise ValueError("end must be after start and chunk must be positive")

        expected: list[tuple[datetime, datetime]] = []
        current = start
        while current < end:
            chunk_end = min(current + chunk, end)
            expected.append((current, chunk_end))
            current = chunk_end

        failures: list[str] = []
        warnings: list[str] = []
        mismatches: list[dict[str, Any]] = []
        chunk_rows: list[dict[str, Any]] = []
        all_ticks: list[tuple[int, float, float, int]] = []
        expected_names: set[str] = set()
        completed = closed = missing = 0

        for chunk_start, chunk_end in expected:
            parquet, lineage_path = self._paths(chunk_start, chunk_end)
            expected_names.update((parquet.name, lineage_path.name))
            closed_expected = _expected_weekend_closure(chunk_start, chunk_end)
            lineage = self._read_lineage(lineage_path) if lineage_path.exists() else None
            record: dict[str, Any] = {"start": _iso(chunk_start), "end": _iso(chunk_end), "expected_market_closed": closed_expected,
                                      "parquet": parquet.name if parquet.exists() else None,
                                      "lineage": lineage_path.name if lineage_path.exists() else None}
            if lineage is None:
                missing += 1
                failures.append("MISSING_EXPECTED_CHUNK")
                record["status"] = "MISSING"
                chunk_rows.append(record)
                continue
            status = lineage.get("status", "COMPLETED")
            record["status"] = status
            for field, actual, wanted in (
                ("start", self._lineage_time(lineage.get("start")), _iso(chunk_start)),
                ("end", self._lineage_time(lineage.get("end")), _iso(chunk_end)),
                ("pair", lineage.get("pair"), self.pair),
                ("source", lineage.get("source"), EXPECTED_SOURCE),
            ):
                if actual != wanted:
                    mismatches.append({"chunk": record["start"], "field": field, "actual": actual, "expected": wanted})
            if closed_expected:
                closed += 1
                if status != "EXPECTED_MARKET_CLOSED" or lineage.get("tick_count") != 0 or parquet.exists():
                    mismatches.append({"chunk": record["start"], "field": "expected_market_closed", "actual": status,
                                       "expected": "EXPECTED_MARKET_CLOSED lineage-only tick_count=0"})
                chunk_rows.append(record)
                continue
            if status != "COMPLETED" or not parquet.exists():
                missing += 1
                failures.append("MISSING_EXPECTED_TRADING_CHUNK")
                record["status"] = "MISSING_TRADING_CHUNK"
                chunk_rows.append(record)
                continue
            row_count, ticks = self._read_parquet(parquet)
            record["parquet_row_count"] = row_count
            record["lineage_tick_count"] = lineage.get("tick_count")
            if lineage.get("tick_count") != row_count:
                mismatches.append({"chunk": record["start"], "field": "tick_count", "actual": lineage.get("tick_count"), "expected": row_count})
            if row_count == 0:
                failures.append("UNEXPECTED_EMPTY_TRADING_CHUNK")
            completed += 1
            all_ticks.extend(ticks)
            chunk_rows.append(record)

        parquet_files = {path.name for path in self.input_dir.glob(f"{self.symbol}_*.parquet")}
        lineage_files = {path.name for path in self.input_dir.glob(f"{self.symbol}_*.lineage.json")}
        orphan_parquet = sorted(parquet_files - expected_names)
        orphan_lineage = sorted(lineage_files - expected_names)
        if orphan_parquet or orphan_lineage:
            warnings.append("ORPHAN_ARTIFACTS")
        if mismatches:
            failures.append("LINEAGE_MISMATCH")

        quality = self._quality(all_ticks)
        if quality["out_of_order_ticks"]:
            failures.append("OUT_OF_ORDER_TICKS")
        if quality["crossed_quotes"]:
            failures.append("CROSSED_QUOTES")
        if quality["nonpositive_quotes"]:
            failures.append("NONPOSITIVE_QUOTES")
        if quality["duplicate_tick_count"]:
            warnings.append("DUPLICATE_TICKS")
        if quality["suspicious_trading_gaps"]:
            warnings.append("SUSPICIOUS_TRADING_GAPS")
        if quality["extreme_spread_count"]:
            warnings.append("EXTREME_SPREADS")
        if quality["low_density_days"]:
            warnings.append("LOW_TICK_DENSITY")

        # Calendar days are the UTC dates touched by [start, end), never the
        # exclusive end date.  Thus [2026-07-01, 2026-08-01) is exactly 31.
        calendar_days = ((end - timedelta(microseconds=1)).date() - start.date()).days + 1
        coverage = 100.0 * (completed + closed) / len(expected)
        severity = "FAIL" if failures else "WARN" if warnings else "PASS"
        report = {
            "schema_version": SCHEMA_VERSION, "symbol": self.symbol, "pair": self.pair,
            "start": _iso(start), "end": _iso(end), "chunk_seconds": chunk.total_seconds(),
            "thresholds": jsonable(self.config), "severity": severity,
            "failures": sorted(set(failures)), "warnings": sorted(set(warnings)),
            "coverage": {"calendar_days": calendar_days, "expected_chunks": len(expected), "completed_trading_chunks": completed,
                         "expected_market_closed_chunks": closed, "missing_chunks": missing, "percentage": coverage},
            "lineage": {"mismatches": mismatches, "orphan_parquet": orphan_parquet,
                        "orphan_lineage": orphan_lineage},
            "chunks": chunk_rows, "quality": quality,
            "period_summary": {"total_ticks": len(all_ticks), "duplicate_ratio": quality["duplicate_tick_ratio"],
                "equal_timestamp_ratio": quality["equal_timestamp_ratio"], "zero_spread_count": quality["zero_spread_count"],
                "zero_spread_ratio": quality["zero_spread_ratio"],
                "spread_p50": quality["spread_pips"]["p50"], "spread_p95": quality["spread_pips"]["p95"],
                "spread_p99": quality["spread_pips"]["p99"], "spread_max": quality["spread_pips"]["max"],
                "crossed_quotes": quality["crossed_quotes"], "out_of_order_ticks": quality["out_of_order_ticks"],
                "suspicious_trading_gaps": quality["suspicious_trading_gaps"], "lineage_mismatches": len(mismatches)},
        }
        report["report_sha256"] = hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return report

    def _quality(self, ticks: Iterable[tuple[int, float, float, int]]) -> dict[str, Any]:
        rows = list(ticks)
        duplicates = len(rows) - len(set(rows))
        equal = out_of_order = suspicious_gaps = 0
        suspicious_gap_observations: list[dict[str, Any]] = []
        expected_closure_gap_observations: list[dict[str, Any]] = []
        prior: tuple[int, float, float, int] | None = None
        for row in rows:
            timestamp, bid, ask, flags = row
            if prior is not None:
                delta = timestamp - prior[0]
                if delta < 0:
                    out_of_order += 1
                elif delta == 0:
                    equal += 1
                elif delta > self.config.suspicious_gap_ms and not _expected_weekend_closure(_timestamp(prior[0]), _timestamp(timestamp)):
                    prior_instant, next_instant = _timestamp(prior[0]), _timestamp(timestamp)
                    observation = {
                        "previous_tick_timestamp": _iso(prior_instant), "next_tick_timestamp": _iso(next_instant),
                        "gap_duration_ms": delta, "gap_duration_seconds": delta / 1000.0,
                        "utc_date": prior_instant.date().isoformat(), "utc_hour": prior_instant.hour,
                        "touches_expected_market_closure": _touches_expected_weekend_closure(prior_instant, next_instant),
                        "previous_bid": prior[1], "previous_ask": prior[2], "next_bid": bid, "next_ask": ask,
                    }
                    if observation["touches_expected_market_closure"]:
                        expected_closure_gap_observations.append(observation)
                    else:
                        suspicious_gaps += 1
                        suspicious_gap_observations.append(observation)
            prior = row
        nonpositive = sum(bid <= 0 or ask <= 0 for _, bid, ask, _ in rows)
        crossed = sum(ask < bid for _, bid, ask, _ in rows)
        valid_spreads = [(ask - bid) / self.config.pip_size for _, bid, ask, _ in rows if bid > 0 and ask >= bid]
        extreme = [{"timestamp": _iso(_timestamp(timestamp)), "spread_pips": (ask - bid) / self.config.pip_size}
                   for timestamp, bid, ask, _ in rows
                   if bid > 0 and ask >= bid and (ask - bid) / self.config.pip_size >= self.config.extreme_spread_pips]
        zero = sum(spread == 0 for spread in valid_spreads)
        daily_ticks: Counter[str] = Counter()
        daily_duplicates: Counter[str] = Counter()
        hourly_ticks: Counter[int] = Counter()
        daily_spreads: dict[str, list[float]] = defaultdict(list)
        hourly_spreads: dict[int, list[float]] = defaultdict(list)
        zero_by_day: Counter[str] = Counter()
        valid_by_day: Counter[str] = Counter()
        zero_by_hour: Counter[int] = Counter()
        valid_by_hour: Counter[int] = Counter()
        extreme_by_day: Counter[str] = Counter()
        extreme_by_hour: Counter[int] = Counter()
        for row in rows:
            timestamp, bid, ask, _ = row
            instant = _timestamp(timestamp)
            day = instant.date().isoformat()
            if instant.weekday() < 5:
                daily_ticks[day] += 1
            hourly_ticks[instant.hour] += 1
            if bid > 0 and ask >= bid:
                spread = (ask - bid) / self.config.pip_size
                daily_spreads[day].append(spread)
                hourly_spreads[instant.hour].append(spread)
                valid_by_day[day] += 1
                valid_by_hour[instant.hour] += 1
                if spread == 0:
                    zero_by_day[day] += 1
                    zero_by_hour[instant.hour] += 1
                if spread >= self.config.extreme_spread_pips:
                    extreme_by_day[day] += 1
                    extreme_by_hour[instant.hour] += 1
        for row, count in Counter(rows).items():
            if count > 1:
                daily_duplicates[_timestamp(row[0]).date().isoformat()] += count - 1
        median_daily = median(daily_ticks.values()) if daily_ticks else None
        low_days = sorted(day for day, count in daily_ticks.items() if median_daily and count < median_daily * self.config.low_density_fraction_of_median)
        most_affected_hour = min((hour for hour, count in extreme_by_hour.items() if count == max(extreme_by_hour.values())), default=None)
        extreme_count = len(extreme)
        return {
            "timestamp_monotonic": out_of_order == 0, "out_of_order_ticks": out_of_order,
            "equal_timestamp_count": equal, "equal_timestamp_ratio": equal / len(rows) if rows else 0.0,
            "duplicate_tick_count": duplicates, "duplicate_tick_ratio": duplicates / len(rows) if rows else 0.0,
            "duplicate_ticks_by_utc_day": dict(sorted(daily_duplicates.items())), "nonpositive_quotes": nonpositive,
            "crossed_quotes": crossed, "bid_equals_ask_count": zero, "zero_spread_count": zero,
            "zero_spread_ratio": zero / len(valid_spreads) if valid_spreads else 0.0,
            "zero_spread_by_utc_day": {day: {"count": zero_by_day[day], "valid_quote_count": valid_by_day[day],
                "ratio": zero_by_day[day] / valid_by_day[day]} for day in sorted(valid_by_day)},
            "zero_spread_by_utc_hour": {str(hour): {"count": zero_by_hour[hour], "valid_quote_count": valid_by_hour[hour],
                "ratio": zero_by_hour[hour] / valid_by_hour[hour] if valid_by_hour[hour] else 0.0} for hour in range(24)},
            "spread_pips": _spread_summary(valid_spreads), "extreme_spread_count": extreme_count,
            "extreme_spread_observations": extreme,
            "extreme_spread_by_utc_day": dict(sorted(extreme_by_day.items())),
            "extreme_spread_by_utc_hour": {str(hour): extreme_by_hour[hour] for hour in range(24)},
            "extreme_spread_percentage_of_total_ticks": 100.0 * extreme_count / len(rows) if rows else 0.0,
            "extreme_spread_most_affected_utc_hour": most_affected_hour,
            "extreme_spread_percentage_in_most_affected_hour": (100.0 * extreme_by_hour[most_affected_hour] / extreme_count
                if most_affected_hour is not None and extreme_count else 0.0),
            "suspicious_trading_gaps": suspicious_gaps, "suspicious_gap_threshold_ms": self.config.suspicious_gap_ms,
            "suspicious_gap_observations": suspicious_gap_observations,
            "expected_market_closure_gaps": len(expected_closure_gap_observations),
            "expected_market_closure_gap_observations": expected_closure_gap_observations,
            "ticks_per_trading_day": dict(sorted(daily_ticks.items())), "trading_day_ticks_min": min(daily_ticks.values()) if daily_ticks else None,
            "trading_day_ticks_median": median_daily, "trading_day_ticks_max": max(daily_ticks.values()) if daily_ticks else None,
            "low_density_days": low_days, "ticks_by_utc_hour": {str(hour): hourly_ticks.get(hour, 0) for hour in range(24)},
            "spread_by_utc_day": {day: _spread_summary(values) for day, values in sorted(daily_spreads.items())},
            "spread_by_utc_hour": {str(hour): {**_spread_summary(hourly_spreads[hour]),
                "zero_spread_ratio": (sum(x == 0 for x in hourly_spreads[hour]) / len(hourly_spreads[hour]) if hourly_spreads[hour] else 0.0)} for hour in range(24)},
        }

    def write_report(self, report: dict[str, Any], output: str | Path | None = None) -> Path:
        path = Path(output) if output else self.input_dir / f"audit_{self.symbol}_{report['start'][:10].replace('-', '')}_{report['end'][:10].replace('-', '')}.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return path
