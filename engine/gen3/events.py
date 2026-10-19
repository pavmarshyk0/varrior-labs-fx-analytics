"""Causal materialization of the frozen Gen-3 H01 V2 and H02 V3 events.

This module deliberately has no outcome, execution, or calendar dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from math import isfinite, log, sqrt
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .contracts import DatasetRole
from .registry import load_registry

EVENT_SCHEMA_VERSION = "gen3-causal-event/v1"
_MINUTE = timedelta(minutes=1)


class FrozenSemanticError(ValueError):
    """Raised when a frozen production semantic is missing or ambiguous."""


@dataclass(frozen=True)
class Quote:
    timestamp: datetime
    bid: float
    ask: float
    source_index: int = 0

    @property
    def midpoint(self) -> float:
        return (self.bid + self.ask) / 2.0


@dataclass(frozen=True)
class CausalEvent:
    hypothesis_id: str
    event_id: str
    event_at_utc: datetime
    available_at_utc: datetime
    direction: str
    dataset_role: str
    lineage: Mapping[str, str]
    frozen_hashes: Mapping[str, str]
    feature_values: Mapping[str, object]
    quality_flags: tuple[str, ...]
    level_id: str | None = None

    def artifact(self) -> dict:
        return {
            "schema_version": EVENT_SCHEMA_VERSION,
            "hypothesis_id": self.hypothesis_id,
            "event_id": self.event_id,
            "event_at_utc": _z(self.event_at_utc),
            "available_at_utc": _z(self.available_at_utc),
            "direction": self.direction,
            "dataset_role": self.dataset_role,
            "level_id": self.level_id,
            "lineage": dict(self.lineage),
            "frozen_hashes": dict(self.frozen_hashes),
            "feature_values": dict(self.feature_values),
            "quality_flags": list(self.quality_flags),
        }


def _z(value: datetime) -> str:
    _utc(value)
    return value.isoformat().replace("+00:00", "Z")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise FrozenSemanticError("UTC-aware timestamp required")
    return value.astimezone(UTC)


def _quote(value: Quote | Mapping[str, object], index: int) -> Quote:
    if isinstance(value, Quote):
        return Quote(_utc(value.timestamp), float(value.bid), float(value.ask), value.source_index)
    try:
        return Quote(_utc(value["timestamp"]), float(value["bid"]), float(value["ask"]), int(value.get("source_index", index)))
    except (KeyError, TypeError, ValueError) as error:
        raise FrozenSemanticError("quote requires timestamp, bid, and ask") from error


def _ordered(quotes: Iterable[Quote | Mapping[str, object]]) -> list[Quote]:
    # Input order is the immutable source order for equal timestamps.
    rows = [_quote(q, i) for i, q in enumerate(quotes)]
    return [x[1] for x in sorted(enumerate(rows), key=lambda x: (x[1].timestamp, x[0]))]


def _valid(q: Quote) -> bool:
    return isfinite(q.bid) and isfinite(q.ask) and q.bid > 0 and q.ask >= q.bid


def _registry(path: str) -> tuple[dict, dict, dict]:
    registry = load_registry(path)
    rows = {x["hypothesis_id"]: x for x in registry["hypotheses"]}
    required = ("G3_H01_COHERENT_REPRICING_V2", "G3_H02_BREAK_STATE_V3")
    if any(x not in registry.get("active_execution_set", []) or x not in rows for x in required):
        raise FrozenSemanticError("M3B active set is absent")
    h01, h02 = rows[required[0]], rows[required[1]]
    # V3 carries H01 as an immutable reference. Resolve it only through the
    # validated V2 registry and require its frozen hashes to match the V3 row.
    if "executable_definition" not in h01:
        v2 = load_registry(str(Path(path).with_name("tier_a_v2.json")))
        h01_v2 = next(x for x in v2["hypotheses"] if x["hypothesis_id"] == required[0])
        if any(h01.get(k) != h01_v2.get(k) for k in ("feature_definition_hash", "config_hash")):
            raise FrozenSemanticError("H01 immutable-reference hash mismatch")
        h01 = h01_v2
    if "executable_definition" not in h01 or "executable_definition" not in h02:
        raise FrozenSemanticError("active executable definition absent")
    return registry, h01, h02


def _event_id(hypothesis_id: str, at: datetime, direction: str, level_id: str | None) -> str:
    raw = "|".join((hypothesis_id, _z(at), direction, level_id or ""))
    return sha256(raw.encode("utf-8")).hexdigest()


def _hashes(row: Mapping[str, object]) -> dict[str, str]:
    return {"feature_definition_hash": str(row["feature_definition_hash"]), "config_hash": str(row["config_hash"])}


def materialize_h01(quotes: Iterable[Quote | Mapping[str, object]], *, registry_path: str, dataset_role: DatasetRole | str, lineage: Mapping[str, str]) -> list[CausalEvent]:
    """Materialize H01 false-to-true events with the global frozen refractory."""
    _, row, _ = _registry(registry_path)
    d = row["executable_definition"]
    rows = _ordered(quotes)
    role = DatasetRole(dataset_role)
    if role not in (DatasetRole.DISCOVERY, DatasetRole.CONFIRMATION):
        raise FrozenSemanticError("H01 may only materialize DISCOVERY or CONFIRMATION")
    out: list[CausalEvent] = []
    was_true = False
    last_event: datetime | None = None
    for i, current in enumerate(rows):
        start, base_start = current.timestamp - timedelta(seconds=30), current.timestamp - timedelta(minutes=30)
        window = rows[max(0, i - 10000):i + 1]
        window = [q for q in window if start < q.timestamp <= current.timestamp]
        baseline = [q for q in rows[:i] if base_start <= q.timestamp < current.timestamp]
        qualifies = False
        flags: list[str] = []
        if len(window) < d["quality_policy"]["minimum_window_tick_count"]:
            flags.append("BLOCKED_INSUFFICIENT_WINDOW_TICKS")
        elif not all(_valid(q) for q in window):
            flags.append("BLOCKED_INVALID_QUOTE")
        elif any((b.timestamp-a.timestamp).total_seconds() > d["quality_policy"]["maximum_gap_seconds"] for a, b in zip(window, window[1:])):
            flags.append("BLOCKED_MAXIMUM_GAP")
        elif len(baseline) < d["baseline"]["minimum_tick_count"] or not baseline or baseline[0].timestamp > base_start:
            flags.append("BLOCKED_INSUFFICIENT_BASELINE")
        elif not all(_valid(q) for q in baseline):
            flags.append("BLOCKED_INVALID_QUOTE")
        else:
            changes = [(b.midpoint-a.midpoint, b.bid-a.bid, b.ask-a.ask) for a, b in zip(window, window[1:])]
            nonzero = [x for x in changes if x[0] != 0]
            if len(nonzero) < d["dti"]["minimum_nonzero_changes"]:
                flags.append(d["dti"]["insufficient"])
            else:
                up = sum(x[0] > 0 for x in nonzero); down = sum(x[0] < 0 for x in nonzero)
                dti = (up-down)/(up+down)
                eligible = [x for x in changes if x[1] != 0 or x[2] != 0]
                sync = sum((x[1] > 0 and x[2] > 0) or (x[1] < 0 and x[2] < 0) for x in eligible) / len(eligible) if eligible else 0.0
                path = sum(abs(x[0]) for x in changes)
                if path == 0:
                    flags.append(d["er"]["zero_denominator"])
                else:
                    er = abs(window[-1].midpoint-window[0].midpoint)/path
                    median = sorted(q.ask-q.bid for q in baseline)[len(baseline)//2]
                    qualifies = abs(dti) >= d["trigger"]["abs_dti"]["value"] and sync >= d["trigger"]["sync"]["value"] and er >= d["trigger"]["er"]["value"] and (current.ask-current.bid) <= median
                    values = {"dti": dti, "sync": sync, "path_efficiency": er, "window_median_spread": sorted(q.ask-q.bid for q in window)[len(window)//2], "baseline_median_spread": median, "window_tick_count": len(window), "nonzero_midpoint_changes": len(nonzero)}
        if not qualifies:
            was_true = False
            continue
        if was_true:
            continue
        was_true = True
        if last_event is not None and (current.timestamp-last_event).total_seconds() < d["refractory"]["seconds"]:
            continue
        direction = "LONG" if values["dti"] > 0 else "SHORT"
        out.append(CausalEvent(row["hypothesis_id"], _event_id(row["hypothesis_id"], current.timestamp, direction, None), current.timestamp, current.timestamp, direction, role.value, lineage, _hashes(row), values, tuple(flags)))
        last_event = current.timestamp
    return out


def _minute_closes(rows: Sequence[Quote]) -> dict[datetime, float]:
    """Last valid midpoint in each completed [start,end) minute; gaps remain gaps."""
    closes: dict[datetime, float] = {}
    for q in rows:
        if not _valid(q):
            continue
        start = q.timestamp.replace(second=0, microsecond=0)
        closes[start] = q.midpoint
    return closes


def _history_scale(closes: Mapping[datetime, float], break_at: datetime) -> float | None:
    end = break_at.replace(second=0, microsecond=0)
    # The break minute is not completed at its tick; its close is forbidden.
    starts = [end - _MINUTE * n for n in range(61, 0, -1)]
    if any(s not in closes or closes[s] <= 0 for s in starts):
        return None
    return sqrt(sum(log(closes[b] / closes[a]) ** 2 for a, b in zip(starts, starts[1:])))


def _category(level: float) -> tuple[str, Decimal] | None:
    value = Decimal(str(level)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    units = int((value / Decimal("0.0001")).to_integral_value())
    for name, step in (("FIGURE", 100), ("HALF_FIGURE", 50), ("TEN_PIP", 10), ("FIVE_PIP", 5)):
        if units % step == 0:
            return name, value
    return None


def _crossed_levels(previous: float, current: float) -> list[tuple[str, float, int]]:
    if current == previous:
        return []
    lo, hi = sorted((Decimal(str(previous)), Decimal(str(current))))
    first = (lo / Decimal("0.0001")).to_integral_value(rounding="ROUND_FLOOR") + 1
    last = (hi / Decimal("0.0001")).to_integral_value(rounding="ROUND_FLOOR")
    values = [float(Decimal(n) * Decimal("0.0001")) for n in range(int(first), int(last) + 1)]
    if current < previous:
        values.reverse()
    sign = 1 if current > previous else -1
    return [(cat[0], float(cat[1]), sign) for x in values if (cat := _category(x)) is not None]


def _post_closes(closes: Mapping[datetime, float], start: datetime, count: int) -> list[tuple[datetime, float]] | None:
    result = [(start + _MINUTE * i, closes.get(start + _MINUTE * i)) for i in range(count)]
    return None if any(value is None or value <= 0 for _, value in result) else result


def materialize_h02(quotes: Iterable[Quote | Mapping[str, object]], *, registry_path: str, dataset_role: DatasetRole | str, lineage: Mapping[str, str]) -> list[CausalEvent]:
    """Materialize the V3 log-space BREAK→ACCEPT/REJECT states, fail-closed."""
    _, _, row = _registry(registry_path)
    d = row["executable_definition"]
    rows = _ordered(quotes); closes = _minute_closes(rows); role = DatasetRole(dataset_role)
    if role not in (DatasetRole.DISCOVERY, DatasetRole.CONFIRMATION):
        raise FrozenSemanticError("H02 may only materialize DISCOVERY or CONFIRMATION")
    output: list[CausalEvent] = []; emitted: set[str] = set(); refractory: dict[tuple[float, int], datetime] = {}
    previous: Quote | None = None
    for q in rows:
        if not _valid(q):
            previous = None
            continue
        if previous is None:
            previous = q; continue
        scale = _history_scale(closes, q.timestamp)
        if scale is None or scale == 0:
            previous = q; continue
        g = log(q.ask / q.bid)
        for category, level, sign in _crossed_levels(previous.midpoint, q.midpoint):
            key = (level, sign)
            if key in refractory and q.timestamp - refractory[key] < timedelta(minutes=d["refractory"]["minutes"]):
                continue
            distance = sign * (log(q.midpoint) - log(level))
            threshold = max(0.10 * scale, g)
            if distance < threshold:  # equality qualifies.
                continue
            buffer = max(0.05 * scale, 0.5 * g)
            post_start = q.timestamp.replace(second=0, microsecond=0) + _MINUTE
            accept = _post_closes(closes, post_start, d["acceptance"]["post_break_closes"])
            accepted = bool(accept) and sum(sign * (log(c / level)) >= buffer for _, c in accept) >= d["acceptance"]["minimum_count"] and sign * log(accept[-1][1] / level) >= buffer
            first_five = _post_closes(closes, post_start, d["rejection"]["return_within_post_break_minutes"])
            returned = next(((at, c) for at, c in (first_five or []) if sign * log(c / level) <= -buffer), None)
            reject = None if returned is None else _post_closes(closes, returned[0] + _MINUTE, d["rejection"]["confirmation_closes_after_return"])
            rejected = bool(reject) and sum(sign * log(c / level) <= -buffer for _, c in reject) >= d["rejection"]["minimum_count"] and sign * log(reject[-1][1] / level) <= -buffer
            # Both classifications for one break are contradictory and never emitted.
            if accepted and rejected:
                continue
            if not accepted and not rejected:
                continue
            state, confirmation = ("ACCEPTANCE", accept[-1][0] + _MINUTE) if accepted else ("REJECTION", reject[-1][0] + _MINUTE)
            direction = "LONG" if sign > 0 else "SHORT"
            level_id = f"{category}:{level:.4f}"
            event_id = _event_id(row["hypothesis_id"], q.timestamp, direction, level_id)
            if event_id in emitted:
                continue
            values = {"state": state, "level_category": category, "level": level, "oriented_log_distance": distance, "volatility_scale": scale, "log_spread": g, "normalized_penetration": distance / scale, "inside_buffer": buffer, "raw_spread_diagnostic": q.ask-q.bid, "break_at_utc": _z(q.timestamp), "classification_completed_at_utc": _z(confirmation)}
            output.append(CausalEvent(row["hypothesis_id"], event_id, q.timestamp, confirmation, direction, role.value, lineage, _hashes(row), values, (), level_id))
            emitted.add(event_id); refractory[key] = q.timestamp
        previous = q
    return output


def artifacts(events: Iterable[CausalEvent]) -> list[dict]:
    """Stable, duplicate-free event-artifact serialization."""
    result = sorted((event.artifact() for event in events), key=lambda x: (x["available_at_utc"], x["event_at_utc"], x["event_id"]))
    if len({x["event_id"] for x in result}) != len(result):
        raise FrozenSemanticError("duplicate event identifier")
    return result
