"""Fail-closed scheduled-calendar adapter; it never reads actual/surprise data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping

from .temporal import InvalidTemporalContext, require_utc, utc_text

class CalendarError(ValueError): pass
class CalendarAvailabilityError(CalendarError): pass

SCHEMA = "gen3-economic-calendar/v1"
_EVENT_TYPES = {"SCHEDULED_MACRO"}; _IMPORTANCE = {"LOW", "MEDIUM", "HIGH"}

def _time(value: Any) -> datetime:
    if not isinstance(value, str): raise CalendarError("calendar timestamp must be text")
    try: return require_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (ValueError, InvalidTemporalContext) as error: raise CalendarError("calendar timestamp must be UTC") from error

def _event(row: Mapping[str, Any]) -> dict[str, Any]:
    required = {"event_id", "scheduled_at_utc", "event_type", "currency", "importance", "source", "known_at_utc", "calendar_version"}
    if not required.issubset(row) or row["event_type"] not in _EVENT_TYPES or row["importance"] not in _IMPORTANCE:
        raise CalendarError("unsupported or malformed calendar event")
    scheduled, known = _time(row["scheduled_at_utc"]), _time(row["known_at_utc"])
    if known > scheduled or not all(isinstance(row[key], str) and row[key] for key in required - {"scheduled_at_utc", "known_at_utc"}):
        raise CalendarError("invalid calendar event")
    return {"event_id": row["event_id"], "scheduled_at_utc": utc_text(scheduled), "event_type": row["event_type"],
            "currency": row["currency"], "importance": row["importance"], "source": row["source"],
            "source_event_id": row.get("source_event_id"), "known_at_utc": utc_text(known), "calendar_version": row["calendar_version"]}

@dataclass(frozen=True)
class EconomicCalendarAdapter:
    calendar_version: str
    generated_at_utc: datetime
    events: tuple[dict[str, Any], ...]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "EconomicCalendarAdapter":
        if set(payload) != {"schema_version", "calendar_version", "generated_at_utc", "events"} or payload["schema_version"] != SCHEMA:
            raise CalendarError("unknown calendar schema version")
        generated = _time(payload["generated_at_utc"])
        if not isinstance(payload["events"], list) or not isinstance(payload["calendar_version"], str): raise CalendarError("invalid calendar payload")
        events = [_event(row) for row in payload["events"]]
        if len({row["event_id"] for row in events}) != len(events): raise CalendarError("duplicate event ID")
        normalized = {(row["scheduled_at_utc"], row["event_type"], row["currency"], row["source"], row["source_event_id"]) for row in events}
        if len(normalized) != len(events): raise CalendarError("duplicate normalized event")
        if any(row["calendar_version"] != payload["calendar_version"] for row in events): raise CalendarError("event calendar version mismatch")
        return cls(payload["calendar_version"], generated, tuple(sorted(events, key=lambda row: (row["scheduled_at_utc"], row["event_id"]))))

    def context(self, timestamp: datetime, *, max_age_hours: int, buckets_minutes: Iterable[Iterable[int]]) -> dict[str, Any]:
        timestamp = require_utc(timestamp)
        if self.generated_at_utc > timestamp: raise CalendarAvailabilityError("calendar snapshot unavailable at evaluation time")
        if (timestamp - self.generated_at_utc).total_seconds() > max_age_hours * 3600:
            raise CalendarAvailabilityError("calendar snapshot is stale")
        known = [row for row in self.events if _time(row["known_at_utc"]) <= timestamp]
        before = [row for row in known if _time(row["scheduled_at_utc"]) <= timestamp]
        after = [row for row in known if _time(row["scheduled_at_utc"]) > timestamp]
        previous = max(before, key=lambda row: (_time(row["scheduled_at_utc"]), row["event_id"]), default=None)
        following = min(after, key=lambda row: (_time(row["scheduled_at_utc"]), row["event_id"]), default=None)
        def minutes(row): return None if row is None else round((timestamp - _time(row["scheduled_at_utc"])).total_seconds() / 60)
        delta_candidates = [(row, minutes(row)) for row in known]
        active = [(row, delta) for row, delta in delta_candidates if any(start <= delta < end for start, end in buckets_minutes)]
        active.sort(key=lambda item: (abs(item[1]), item[0]["event_id"]))
        return {"calendar_freshness": "FRESH", "calendar_source": sorted({row["source"] for row in self.events}),
                "calendar_version": self.calendar_version, "previous_scheduled_event": previous,
                "next_scheduled_event": following, "minutes_since_previous_event": minutes(previous),
                "minutes_until_next_event": None if following is None else -minutes(following),
                "macro_hazard_state": "SCHEDULED_EVENT_HAZARD" if active else "NO_SCHEDULED_EVENT_HAZARD",
                "active_hazard_events": [{"event_id": row["event_id"], "minutes_from_event": delta} for row, delta in active]}
