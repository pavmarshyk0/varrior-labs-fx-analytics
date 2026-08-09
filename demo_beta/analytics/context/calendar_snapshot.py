"""Immutable historical economic-calendar snapshots and post-release inputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from statistics import median
from typing import Any, Sequence

from ...contracts import Tick
from .event_time_hazard import CalendarSnapshot, Impact, MacroEvent, _utc


class CalendarSnapshotValidationError(ValueError):
    """The on-disk snapshot is not a reproducible historical calendar input."""


def _required(mapping: dict[str, Any], name: str) -> Any:
    if name not in mapping or mapping[name] in (None, ""):
        raise CalendarSnapshotValidationError(f"missing calendar field: {name}")
    return mapping[name]


def _time(value: Any, name: str):
    if not isinstance(value, str):
        raise CalendarSnapshotValidationError(f"{name} must be an ISO-8601 timestamp string")
    try:
        from datetime import datetime
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _utc(parsed, name)
    except ValueError as exc:
        raise CalendarSnapshotValidationError(f"invalid {name}: {value!r}") from exc


def load_calendar_snapshot(path: str | Path) -> CalendarSnapshot:
    """Load a versioned snapshot without accepting revised/future-looking fields.

    Expected schema: ``snapshot_id``, ``as_of``, ``source`` and an ``events``
    array. Each event has ``event_id``, ``event_code``, ``name``, ``currency``,
    ``scheduled_at`` and ``impact``. Optional event ``source`` defaults to the
    snapshot source. Actual/revised values are intentionally not accepted.
    """
    source_path = Path(path)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalendarSnapshotValidationError(f"cannot read calendar snapshot {source_path}") from exc
    if not isinstance(payload, dict):
        raise CalendarSnapshotValidationError("calendar snapshot root must be an object")
    allowed = {"snapshot_id", "as_of", "source", "events"}
    unknown = set(payload) - allowed
    if unknown:
        raise CalendarSnapshotValidationError(f"unsupported calendar snapshot fields: {sorted(unknown)}")
    source = str(_required(payload, "source"))
    raw_events = _required(payload, "events")
    if not isinstance(raw_events, list):
        raise CalendarSnapshotValidationError("events must be an array")
    events: list[MacroEvent] = []
    for index, raw in enumerate(raw_events):
        if not isinstance(raw, dict):
            raise CalendarSnapshotValidationError(f"events[{index}] must be an object")
        allowed_event = {"event_id", "event_code", "name", "currency", "scheduled_at", "impact", "source"}
        unknown_event = set(raw) - allowed_event
        if unknown_event:
            raise CalendarSnapshotValidationError(f"unsupported events[{index}] fields: {sorted(unknown_event)}")
        try:
            impact = Impact(str(_required(raw, "impact")).upper())
            events.append(MacroEvent(
                event_id=str(_required(raw, "event_id")), event_code=str(_required(raw, "event_code")),
                name=str(_required(raw, "name")), currency=str(_required(raw, "currency")).upper(),
                scheduled_at=_time(_required(raw, "scheduled_at"), f"events[{index}].scheduled_at"),
                impact=impact, source=str(raw.get("source") or source),
            ))
        except ValueError as exc:
            raise CalendarSnapshotValidationError(f"invalid events[{index}]") from exc
    if any(events[i].scheduled_at > events[i + 1].scheduled_at for i in range(len(events) - 1)):
        raise CalendarSnapshotValidationError("events must be sorted by scheduled_at")
    return CalendarSnapshot(
        snapshot_id=str(_required(payload, "snapshot_id")), as_of=_time(_required(payload, "as_of"), "as_of"),
        source=source, events=tuple(events),
    )


@dataclass(frozen=True, slots=True)
class PostJumpStabilisationInputs:
    """Observed-only post-release microstructure inputs; never a trading decision."""

    event_id: str
    observation_end_msc: int
    elapsed_seconds: float
    tick_count: int
    median_spread_pips: float | None
    realized_range_pips: float | None
    status: str = "RESEARCH"


def post_jump_stabilisation_inputs(
    event: MacroEvent, ticks: Sequence[Tick], *, observation_end_msc: int, pip_size: float = 0.0001
) -> PostJumpStabilisationInputs:
    """Summarise ticks observed after a release up to an explicit cutoff.

    The cutoff prevents future-tick leakage. Callers decide how this research
    feature is evaluated; it has no direction, vote, veto, or execution path.
    """
    release_msc = int(event.scheduled_at.timestamp() * 1000)
    if observation_end_msc < release_msc:
        raise ValueError("observation_end_msc cannot precede the release")
    observed = [tick for tick in ticks if release_msc <= tick.time_msc <= observation_end_msc]
    spreads = [tick.spread / pip_size for tick in observed]
    mids = [tick.mid for tick in observed]
    return PostJumpStabilisationInputs(
        event_id=event.event_id, observation_end_msc=observation_end_msc,
        elapsed_seconds=(observation_end_msc - release_msc) / 1000.0, tick_count=len(observed),
        median_spread_pips=median(spreads) if spreads else None,
        realized_range_pips=((max(mids) - min(mids)) / pip_size) if mids else None,
    )
