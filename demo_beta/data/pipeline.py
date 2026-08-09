"""Resumable, validation-gated historical MT5 tick ingestion."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

from ..contracts import Tick, jsonable
from .mt5 import MT5TickCollector
from .validation import DataQualityViolation, TickFeedValidator


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("pipeline bounds must be timezone-aware")
    return value.astimezone(UTC)


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class LineageMetadata:
    """Auditable provenance for one immutable processed chunk."""
    lineage_id: str
    pair: str
    source: str
    start: datetime
    end: datetime
    tick_count: int
    quality: dict[str, Any]
    status: str = "COMPLETED"
    calendar_snapshot_id: str | None = None
    config_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineChunk:
    start: datetime
    end: datetime
    parquet_path: Path | None
    lineage_path: Path
    resumed: bool
    status: str = "COMPLETED"


class HistoricalTickPipeline:
    """Collect bounded UTC chunks, reject bad feeds, then atomically mark done."""

    def __init__(self, collector: MT5TickCollector, output_dir: str | Path, *, validator: TickFeedValidator | None = None,
                 calendar_snapshot_id: str | None = None, config_text: str | None = None,
                 parquet_writer: Callable[[Sequence[Tick], Path], Path] | None = None,
                 record_unavailable_history: bool = False) -> None:
        self.collector = collector
        self.output_dir = Path(output_dir)
        self.validator = validator or TickFeedValidator()
        self.calendar_snapshot_id = calendar_snapshot_id
        self.config_sha256 = hashlib.sha256((config_text or "").encode()).hexdigest() if config_text else None
        self.parquet_writer = parquet_writer
        self.record_unavailable_history = record_unavailable_history

    @staticmethod
    def _name(start: datetime, end: datetime) -> str:
        return f"EURUSD_{start:%Y%m%dT%H%M%SZ}_{end:%Y%m%dT%H%M%SZ}"

    def _paths(self, start: datetime, end: datetime) -> tuple[Path, Path]:
        name = self._name(start, end)
        return self.output_dir / f"{name}.parquet", self.output_dir / f"{name}.lineage.json"

    @staticmethod
    def _is_expected_weekend_closure(start: datetime, end: datetime) -> bool:
        """Return whether the complete half-open UTC interval is Sat/Sun.

        EUR/USD's verified MT5 weekend closure covers full UTC Saturday and
        Sunday.  This deliberately does not suppress an interval which merely
        starts or ends in the closure but includes any trading-period instant.
        """
        if start.weekday() not in (5, 6):
            return False
        closure_end = datetime(start.year, start.month, start.day, tzinfo=UTC) + timedelta(
            days=7 - start.weekday()
        )
        return end <= closure_end

    def _write_expected_market_closed(
        self, lineage_path: Path, start: datetime, end: datetime, quality: Any
    ) -> None:
        payload = {
            "pair": "EUR_USD", "source": "MT5_COPY_TICKS_ALL", "start": start, "end": end,
            "tick_count": 0, "quality": jsonable(quality), "status": "EXPECTED_MARKET_CLOSED",
            "calendar_snapshot_id": self.calendar_snapshot_id, "config_sha256": self.config_sha256,
        }
        lineage = LineageMetadata(
            lineage_id=_hash(jsonable(payload)), pair="EUR_USD", source="MT5_COPY_TICKS_ALL", start=start, end=end,
            tick_count=0, quality=jsonable(quality), status="EXPECTED_MARKET_CLOSED",
            calendar_snapshot_id=self.calendar_snapshot_id, config_sha256=self.config_sha256,
        )
        temp = lineage_path.with_suffix(lineage_path.suffix + ".tmp")
        temp.write_text(json.dumps(jsonable(lineage), indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(lineage_path)

    def _write_unavailable_history(self, lineage_path: Path, start: datetime, end: datetime, quality: Any) -> None:
        lineage = LineageMetadata(lineage_id=_hash(jsonable({"start": start, "end": end, "status": "NO_BROKER_HISTORY"})),
            pair="EUR_USD", source="MT5_COPY_TICKS_ALL", start=start, end=end, tick_count=0,
            quality=jsonable(quality), status="NO_BROKER_HISTORY", calendar_snapshot_id=self.calendar_snapshot_id,
            config_sha256=self.config_sha256)
        temp = lineage_path.with_suffix(lineage_path.suffix + ".tmp")
        temp.write_text(json.dumps(jsonable(lineage), indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(lineage_path)

    @staticmethod
    def _is_resumable_expected_closure(lineage_path: Path) -> bool:
        try:
            lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return lineage.get("status") in {"EXPECTED_MARKET_CLOSED", "NO_BROKER_HISTORY"} and lineage.get("tick_count") == 0

    def _write_chunk(self, ticks: list[Tick], parquet_path: Path, lineage_path: Path, start: datetime, end: datetime) -> None:
        quality = self.validator.validate(ticks)
        if not quality.valid:
            raise DataQualityViolation(f"refusing pipeline chunk: {', '.join(quality.hard_failures)}")
        if self.parquet_writer is None:
            from data_ingestion.mt5_collector import write_validated_parquet
            write_validated_parquet(ticks, parquet_path, validator=self.validator)
        else:
            self.parquet_writer(ticks, parquet_path)
        payload = {
            "pair": "EUR_USD", "source": "MT5_COPY_TICKS_ALL", "start": start, "end": end,
            "tick_count": len(ticks), "quality": jsonable(quality),
            "calendar_snapshot_id": self.calendar_snapshot_id, "config_sha256": self.config_sha256,
        }
        lineage = LineageMetadata(
            lineage_id=_hash(jsonable(payload)), pair="EUR_USD", source="MT5_COPY_TICKS_ALL", start=start, end=end,
            tick_count=len(ticks), quality=jsonable(quality), calendar_snapshot_id=self.calendar_snapshot_id,
            config_sha256=self.config_sha256,
        )
        temp = lineage_path.with_suffix(lineage_path.suffix + ".tmp")
        temp.write_text(json.dumps(jsonable(lineage), indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(lineage_path)

    def collect(self, start: datetime, end: datetime, *, chunk: timedelta = timedelta(days=1)) -> list[PipelineChunk]:
        start, end = _utc(start), _utc(end)
        if end <= start or chunk <= timedelta(0):
            raise ValueError("end must be after start and chunk must be positive")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        results: list[PipelineChunk] = []
        current = start
        while current < end:
            chunk_end = min(current + chunk, end)
            parquet_path, lineage_path = self._paths(current, chunk_end)
            if parquet_path.exists() and lineage_path.exists():
                results.append(PipelineChunk(current, chunk_end, parquet_path, lineage_path, True))
            elif (not parquet_path.exists() and lineage_path.exists()
                  and self._is_resumable_expected_closure(lineage_path)):
                status = json.loads(lineage_path.read_text(encoding="utf-8"))["status"]
                results.append(PipelineChunk(current, chunk_end, None, lineage_path, True, status))
            else:
                # A partial artifact is never treated as completed: recollect it.
                ticks = self.collector.collect(current, chunk_end)
                if not ticks and self._is_expected_weekend_closure(current, chunk_end):
                    quality = self.validator.validate(ticks)
                    self._write_expected_market_closed(lineage_path, current, chunk_end, quality)
                    results.append(PipelineChunk(current, chunk_end, None, lineage_path, False, "EXPECTED_MARKET_CLOSED"))
                elif not ticks and self.record_unavailable_history:
                    quality = self.validator.validate(ticks)
                    self._write_unavailable_history(lineage_path, current, chunk_end, quality)
                    results.append(PipelineChunk(current, chunk_end, None, lineage_path, False, "NO_BROKER_HISTORY"))
                else:
                    self._write_chunk(ticks, parquet_path, lineage_path, current, chunk_end)
                    results.append(PipelineChunk(current, chunk_end, parquet_path, lineage_path, False))
            current = chunk_end
        return results
