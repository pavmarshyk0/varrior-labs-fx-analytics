"""Deterministic, metadata-only UTC-to-civil-time context for Gen-3 M2."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


class InvalidTemporalContext(ValueError): pass
class TemporalConfigError(ValueError): pass


def require_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise InvalidTemporalContext("timestamp must be timezone-aware and exactly UTC")
    return value


def utc_text(value: datetime) -> str:
    return require_utc(value).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def config_projection(config: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key != "config_hash"}


def config_hash(config: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(config_projection(config)).encode("utf-8")).hexdigest()


def load_temporal_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"schema_version", "config_version", "supported_iana_zones", "boundary_convention",
                "windows", "anchors", "calendar", "hazard", "config_hash"}
    if set(config) != required or config["schema_version"] != "gen3-temporal-context/v1":
        raise TemporalConfigError("unsupported temporal config schema")
    if config["boundary_convention"] != "[start,end)" or config["config_hash"] != config_hash(config):
        raise TemporalConfigError("temporal config hash or boundary convention mismatch")
    if set(config["supported_iana_zones"]) != {"UTC", "Europe/London", "America/New_York", "Asia/Tokyo"}:
        raise TemporalConfigError("unexpected IANA zone set")
    return config


def _clock(value: str) -> time:
    return time.fromisoformat(value)


def _active(local: datetime, definition: Mapping[str, str]) -> bool:
    start, end, current = _clock(definition["start"]), _clock(definition["end"]), local.timetz().replace(tzinfo=None)
    return start <= current < end if start < end else current >= start or current < end


def _anchor_minutes(timestamp: datetime, zone: ZoneInfo, anchor: str) -> int:
    local = timestamp.astimezone(zone)
    anchor_local = datetime.combine(local.date(), _clock(anchor), tzinfo=zone)
    return round((timestamp - anchor_local.astimezone(UTC)).total_seconds() / 60)


def _relation(london: datetime, new_york: datetime) -> str:
    offsets = (int(london.utcoffset().total_seconds() // 60), int(new_york.utcoffset().total_seconds() // 60))
    return {(0, -300): "EU_US_STANDARD_RELATION", (60, -240): "EU_US_SUMMER_RELATION",
            (0, -240): "US_DST_EU_STANDARD_MISMATCH", (60, -300): "EU_DST_US_STANDARD_MISMATCH"}.get(
                offsets, "UNEXPECTED_OFFSET_RELATION")


@dataclass(frozen=True)
class MarketClock:
    config: Mapping[str, Any]

    def context(self, timestamp: datetime) -> dict[str, Any]:
        timestamp = require_utc(timestamp)
        london, new_york, tokyo = (timestamp.astimezone(ZoneInfo(name)) for name in
                                   ("Europe/London", "America/New_York", "Asia/Tokyo"))
        flags = {name: _active(timestamp.astimezone(ZoneInfo(spec["zone"])), spec)
                 for name, spec in sorted(self.config["windows"].items())}
        flags["london_ny_overlap"] = flags["london_active"] and flags["new_york_active"]
        minutes = {name: _anchor_minutes(timestamp, ZoneInfo(spec["zone"]), spec["time"])
                   for name, spec in sorted(self.config["anchors"].items())}
        return {"timestamp_utc": utc_text(timestamp), "london_timestamp": london.isoformat(),
                "new_york_timestamp": new_york.isoformat(), "tokyo_timestamp": tokyo.isoformat(),
                "weekday": timestamp.strftime("%A"),
                "local_dates": {"london": london.date().isoformat(), "new_york": new_york.date().isoformat(),
                                "tokyo": tokyo.date().isoformat()},
                "utc_offsets_minutes": {"london": int(london.utcoffset().total_seconds() // 60),
                                        "new_york": int(new_york.utcoffset().total_seconds() // 60),
                                        "tokyo": int(tokyo.utcoffset().total_seconds() // 60)},
                "dst_relationship": _relation(london, new_york), "active_windows": flags,
                "minutes_from_anchors": minutes}

@dataclass(frozen=True)
class EventTimeHazardContext:
    config: Mapping[str, Any]
    calendar: Any | None = None
    def context(self, timestamp: datetime, *, dataset_role: Any = None) -> dict[str, Any]:
        del dataset_role
        output = {"schema_version": "gen3-event-time-context/v1", **MarketClock(self.config).context(timestamp),
                  "temporal_config_hash": self.config["config_hash"], "warnings": [],
                  "limitations": ["Context/risk metadata only; no price, outcome, or directional decision is read or emitted."],
                  "risk_decision_state": "BLOCKED_POLICY_NOT_FROZEN"}
        if self.calendar is None:
            output.update({"calendar_freshness":"UNAVAILABLE","calendar_source":[],"calendar_version":None,
                "previous_scheduled_event":None,"next_scheduled_event":None,"minutes_since_previous_event":None,
                "minutes_until_next_event":None,"macro_hazard_state":"BLOCKED_NO_CALENDAR_DATA","active_hazard_events":[]})
        else:
            output.update(self.calendar.context(timestamp, max_age_hours=self.config["calendar"]["max_age_hours"], buckets_minutes=self.config["hazard"]["buckets_minutes"]))
        return output
    def context_from_row(self, row: Mapping[str, Any], *, timestamp_field: str = "timestamp_utc", dataset_role: Any = None) -> dict[str, Any]:
        value = row[timestamp_field]
        if not isinstance(value, datetime): raise InvalidTemporalContext("row timestamp must be a UTC datetime")
        return self.context(value, dataset_role=dataset_role)
