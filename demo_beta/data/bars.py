"""Deterministic UTC MT5 tick-to-bar construction; this module never alters ticks."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from ..contracts import Tick, jsonable
from .mt5_audit import _expected_weekend_closure, _percentile, _touches_expected_weekend_closure

SCHEMA_VERSION = "mt5-bars/v1"
TIMEFRAME_MS = {"M5": 300_000, "M15": 900_000, "H1": 3_600_000}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("bar bounds must be timezone-aware")
    return value.astimezone(UTC)


def _iso_msc(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, UTC).isoformat().replace("+00:00", "Z")


def _p(values: list[float], q: float) -> float | None:
    return _percentile(values, q)


@dataclass(slots=True)
class _Bar:
    start_msc: int
    end_msc: int
    timeframe: str
    ticks: list[Tick] = field(default_factory=list)
    spreads: list[float] = field(default_factory=list)
    max_gap_ms: int = 0
    flags: set[str] = field(default_factory=set)
    suspicious_gap_observations: list[dict[str, Any]] = field(default_factory=list)
    empty_constituent_count: int = 0

    def row(self, symbol: str, pip_size: float) -> dict[str, Any]:
        first, last = self.ticks[0], self.ticks[-1]
        bid = [x.bid for x in self.ticks]
        ask = [x.ask for x in self.ticks]
        zero = sum(x == 0 for x in self.spreads)
        return {"bar_start": _iso_msc(self.start_msc), "bar_end": _iso_msc(self.end_msc), "symbol": symbol,
                "timeframe": self.timeframe, "bid_open": bid[0], "bid_high": max(bid), "bid_low": min(bid), "bid_close": bid[-1],
                "ask_open": ask[0], "ask_high": max(ask), "ask_low": min(ask), "ask_close": ask[-1],
                "tick_count": len(self.ticks), "first_tick_timestamp": _iso_msc(first.time_msc), "last_tick_timestamp": _iso_msc(last.time_msc),
                "spread_pips_min": min(self.spreads), "spread_pips_median": median(self.spreads), "spread_pips_p95": _p(self.spreads, .95),
                "spread_pips_max": max(self.spreads), "zero_spread_tick_count": zero, "zero_spread_ratio": zero / len(self.ticks),
                "max_intertick_gap_ms": self.max_gap_ms, "empty_constituent_count": self.empty_constituent_count,
                "suspicious_gap_count": len(self.suspicious_gap_observations),
                "suspicious_gap_observations": self.suspicious_gap_observations,
                "quality_flags": sorted(self.flags)}


@dataclass(frozen=True, slots=True)
class BarBuildConfig:
    pip_size: float = .0001
    suspicious_gap_ms: int = 60_000
    extreme_spread_pips: float = 5.0
    zero_spread_heavy_ratio: float = .50
    def __post_init__(self) -> None:
        if self.pip_size <= 0 or self.suspicious_gap_ms <= 0 or self.extreme_spread_pips <= 0 or not 0 <= self.zero_spread_heavy_ratio <= 1:
            raise ValueError("invalid bar build configuration")


class MT5BarBuilder:
    def __init__(self, *, symbol: str = "EURUSD", config: BarBuildConfig | None = None) -> None:
        self.symbol, self.config = symbol, config or BarBuildConfig()

    def build(self, ticks: list[Tick], start: datetime, end: datetime, timeframes: tuple[str, ...] = ("M5", "M15", "H1"), *, source_dataset: str | None = None, source_audit_report: str | None = None) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        start, end = _utc(start), _utc(end)
        requested = tuple(timeframes)
        if not requested or any(x not in TIMEFRAME_MS for x in requested):
            raise ValueError("timeframes must be non-empty M5/M15/H1 values")
        if start.microsecond or end.microsecond or int(start.timestamp() * 1000) % TIMEFRAME_MS["M5"] or int(end.timestamp() * 1000) % TIMEFRAME_MS["M5"]:
            raise ValueError("bar build bounds must align to M5 UTC boundaries")
        if any(t.time_msc < int(start.timestamp() * 1000) or t.time_msc >= int(end.timestamp() * 1000) for t in ticks):
            raise ValueError("input ticks must lie within [start, end)")
        if any(ticks[i].time_msc < ticks[i - 1].time_msc for i in range(1, len(ticks))):
            raise ValueError("input ticks must be monotonic; raw tick order is immutable")
        m5 = self._from_ticks(ticks, start, end, "M5")
        bars: dict[str, list[_Bar]] = {"M5": m5}
        if "M15" in requested or "H1" in requested:
            bars["M15"] = self._aggregate(m5, start, end, "M15")
        if "H1" in requested:
            bars["H1"] = self._aggregate(bars["M15"], start, end, "H1")
        selected = {tf: [bar.row(self.symbol, self.config.pip_size) for bar in bars[tf]] for tf in requested}
        report = self._validate(bars, selected, ticks, start, end, requested)
        report["source_dataset"] = source_dataset
        report["source_audit_report"] = source_audit_report
        return selected, report

    def _from_ticks(self, ticks: list[Tick], start: datetime, end: datetime, timeframe: str) -> list[_Bar]:
        size = TIMEFRAME_MS[timeframe]
        grouped: dict[int, _Bar] = {}
        previous: Tick | None = None
        for tick in ticks:
            bucket = tick.time_msc - tick.time_msc % size
            bar = grouped.setdefault(bucket, _Bar(bucket, bucket + size, timeframe))
            bar.ticks.append(tick); bar.spreads.append((tick.ask - tick.bid) / self.config.pip_size)
            if previous is not None:
                gap = tick.time_msc - previous.time_msc
                bar.max_gap_ms = max(bar.max_gap_ms, gap)
                if gap > self.config.suspicious_gap_ms and not _touches_expected_weekend_closure(previous.timestamp, tick.timestamp):
                    bar.flags.add("HAS_SUSPICIOUS_GAP")
                    bar.suspicious_gap_observations.append({"previous_tick_timestamp": _iso_msc(previous.time_msc),
                        "next_tick_timestamp": _iso_msc(tick.time_msc), "gap_duration_ms": gap,
                        "gap_duration_seconds": gap / 1000.0})
            previous = tick
        for bar in grouped.values():
            if any(x >= self.config.extreme_spread_pips for x in bar.spreads): bar.flags.add("EXTREME_SPREAD")
            if sum(x == 0 for x in bar.spreads) / len(bar.spreads) >= self.config.zero_spread_heavy_ratio: bar.flags.add("ZERO_SPREAD_HEAVY")
        return [grouped[key] for key in sorted(grouped)]

    def _aggregate(self, children: list[_Bar], start: datetime, end: datetime, timeframe: str) -> list[_Bar]:
        size = TIMEFRAME_MS[timeframe]
        grouped: dict[int, _Bar] = {}
        for child in children:
            bucket = child.start_msc - child.start_msc % size
            parent = grouped.setdefault(bucket, _Bar(bucket, bucket + size, timeframe))
            parent.ticks.extend(child.ticks); parent.spreads.extend(child.spreads); parent.max_gap_ms = max(parent.max_gap_ms, child.max_gap_ms)
            parent.flags.update(child.flags)
            parent.suspicious_gap_observations.extend(child.suspicious_gap_observations)
        child_size = TIMEFRAME_MS[children[0].timeframe] if children else (TIMEFRAME_MS["M5"] if timeframe == "M15" else TIMEFRAME_MS["M15"])
        for parent in grouped.values():
            expected = size // child_size
            parent.empty_constituent_count = expected - sum(1 for child in children if parent.start_msc <= child.start_msc < parent.end_msc)
            if parent.empty_constituent_count: parent.flags.add("INCOMPLETE_OR_EMPTY_INTERVAL")
            if any(x >= self.config.extreme_spread_pips for x in parent.spreads): parent.flags.add("EXTREME_SPREAD")
            if sum(x == 0 for x in parent.spreads) / len(parent.spreads) >= self.config.zero_spread_heavy_ratio: parent.flags.add("ZERO_SPREAD_HEAVY")
        return [grouped[key] for key in sorted(grouped)]

    def _validate(self, bars: dict[str, list[_Bar]], rows: dict[str, list[dict[str, Any]]], ticks: list[Tick], start: datetime, end: datetime, requested: tuple[str, ...]) -> dict[str, Any]:
        violations: list[str] = []
        for tf in requested:
            for row in rows[tf]:
                if not (row["bid_low"] <= row["bid_open"] <= row["bid_high"] and row["bid_low"] <= row["bid_close"] <= row["bid_high"] and row["ask_low"] <= row["ask_open"] <= row["ask_high"] and row["ask_low"] <= row["ask_close"] <= row["ask_high"]): violations.append(f"OHLC_INVARIANT:{tf}:{row['bar_start']}")
        reconciliation: list[str] = []
        for parent_tf, child_tf in (("M15", "M5"), ("H1", "M15")):
            if parent_tf not in bars or child_tf not in bars: continue
            for parent in bars[parent_tf]:
                children = [child for child in bars[child_tf] if parent.start_msc <= child.start_msc < parent.end_msc]
                if parent.ticks and (len(parent.ticks) != sum(len(x.ticks) for x in children) or parent.ticks[0].bid != children[0].ticks[0].bid or parent.ticks[-1].ask != children[-1].ticks[-1].ask): reconciliation.append(f"RECONCILIATION:{parent_tf}:{parent.start_msc}")
        total_slots = (int(end.timestamp() * 1000) - int(start.timestamp() * 1000)) // TIMEFRAME_MS["M5"]
        populated = len(bars["M5"])
        closure_slots = sum(1 for index in range(total_slots) if _expected_weekend_closure(start + timedelta(milliseconds=index * TIMEFRAME_MS["M5"]), start + timedelta(milliseconds=(index + 1) * TIMEFRAME_MS["M5"])))
        empty_trading = total_slots - populated - closure_slots
        warnings = {flag for row in rows["M5"] for flag in row["quality_flags"] if flag != "INCOMPLETE_OR_EMPTY_INTERVAL"}
        severity = "FAIL" if violations or reconciliation or sum(row["tick_count"] for row in rows["M5"]) != len(ticks) else "WARN" if warnings or empty_trading else "PASS"
        return {"schema_version": SCHEMA_VERSION, "start": start, "end": end, "symbol": self.symbol, "configuration": jsonable(self.config),
                "input_ticks": len(ticks), "m5_tick_count": sum(row["tick_count"] for row in rows["M5"]), "bar_counts": {tf: len(rows[tf]) for tf in requested},
                "populated_bar_counts": {tf: len(rows[tf]) for tf in requested}, "timeframes": list(requested),
                "empty_expected_trading_intervals": empty_trading, "expected_market_closure_intervals": closure_slots,
                "bars_with_suspicious_gaps": sum("HAS_SUSPICIOUS_GAP" in row["quality_flags"] for row in rows["M5"]),
                "suspicious_gap_count": sum(row["suspicious_gap_count"] for row in rows["M5"]),
                "bars_with_extreme_spreads": sum("EXTREME_SPREAD" in row["quality_flags"] for row in rows["M5"]),
                "bars_with_heavy_zero_spread": sum("ZERO_SPREAD_HEAVY" in row["quality_flags"] for row in rows["M5"]),
                "ohlc_invariant_violations": violations, "cross_timeframe_reconciliation_failures": reconciliation, "severity": severity}

    def write(self, bars: dict[str, list[dict[str, Any]]], report: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
        try:
            import pyarrow as pa; import pyarrow.parquet as pq  # type: ignore[import-not-found]
        except ImportError as exc: raise RuntimeError("bar output requires pyarrow") from exc
        root = Path(output_dir) / self.symbol; paths: dict[str, Path] = {}
        for timeframe, rows in bars.items():
            directory = root / timeframe; directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{self.symbol}_{report['start']:%Y%m%dT%H%M%SZ}_{report['end']:%Y%m%dT%H%M%SZ}.parquet"
            pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd"); paths[timeframe] = path
        payload = {**report, "bar_files": {tf: str(path) for tf, path in paths.items()}}
        payload["payload_sha256"] = hashlib.sha256(json.dumps(jsonable(payload), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        lineage = root / f"{self.symbol}_{report['start']:%Y%m%dT%H%M%SZ}_{report['end']:%Y%m%dT%H%M%SZ}.bar-build.json"
        lineage.write_text(json.dumps(jsonable(payload), indent=2, sort_keys=True), encoding="utf-8"); paths["report"] = lineage
        return paths
