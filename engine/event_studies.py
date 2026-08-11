"""Predeclared, non-executable EUR/USD event studies.

The module deliberately studies conditional forward distributions before any
entry/stop/target construction.  Discovery and confirmation outcomes are
reported separately.  For the locked segment only event counts are recorded;
future prices are never read or transformed into outcomes.
"""
from __future__ import annotations

import json
from bisect import bisect_left, insort
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Literal, Mapping, Sequence
from zoneinfo import ZoneInfo

from .exit_ablation_runner import BarDataset, INVALID_FLAGS, _utc
from .research_statistics import block_bootstrap_expectancy_ci

PIP_SIZE = 0.0001
HORIZONS = (1, 3, 6, 12, 24, 36)
DISCOVERY_END = datetime(2025, 8, 1, tzinfo=UTC)
CONFIRMATION_END = datetime(2026, 2, 1, tzinfo=UTC)
M5_SECONDS = 300

OutcomeKind = Literal["DIRECTIONAL", "MAGNITUDE"]


EVENT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "LONDON_OPEN": {"family": "SESSION", "outcome": "DIRECTIONAL", "orientation": 1},
    "NEW_YORK_OPEN": {"family": "SESSION", "outcome": "DIRECTIONAL", "orientation": 1},
    "ASIAN_RANGE_COMPRESSION": {
        "family": "ASIAN_RANGE", "outcome": "MAGNITUDE",
        "definition": "00:00-08:00 UTC range <= trailing 20-session q25 at 08:00 UTC",
    },
    "ASIAN_HIGH_FIRST_BREAK": {
        "family": "ASIAN_RANGE", "outcome": "DIRECTIONAL", "orientation": 1,
        "definition": "first 08:00-12:00 Europe/London M5 high above the completed Asian high",
    },
    "ASIAN_LOW_FIRST_BREAK": {
        "family": "ASIAN_RANGE", "outcome": "DIRECTIONAL", "orientation": -1,
        "definition": "first 08:00-12:00 Europe/London M5 low below the completed Asian low",
    },
    "PDH_FIRST_BREAK": {
        "family": "PDH_PDL", "outcome": "DIRECTIONAL", "orientation": 1,
        "definition": "first M5 high above the most recent completed 17:00 New-York FX-day high",
    },
    "PDL_FIRST_BREAK": {
        "family": "PDH_PDL", "outcome": "DIRECTIONAL", "orientation": -1,
        "definition": "first M5 low below the most recent completed 17:00 New-York FX-day low",
    },
    "VOLATILITY_COMPRESSION_TRANSITION": {
        "family": "VOLATILITY", "outcome": "MAGNITUDE",
        "definition": "12-bar mid range crosses below 0.5x its trailing 288-observation median",
    },
    "EFFICIENT_TREND_IMPULSE": {
        "family": "TREND_PERSISTENCE", "outcome": "DIRECTIONAL",
        "definition": "6-bar move >= trailing median 12-bar range with path efficiency >= 0.65",
    },
    "RANGE_DEVIATION_MEAN_REVERSION": {
        "family": "MEAN_REVERSION", "outcome": "DIRECTIONAL",
        "definition": "range-regime close in outer 20% of its trailing 24-bar range; oriented to trailing mean",
    },
    "HIGH_INTENSITY_COHERENT_BAR_PROXY": {
        "family": "MICROSTRUCTURE_PROXY", "outcome": "DIRECTIONAL",
        "definition": "tick count >= trailing q90, bar efficiency >= 0.70, spread p95 <= trailing median",
        "limitation": "bar-level proxy; not signed trade flow or order-book evidence",
    },
}


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    timestamp: datetime
    entry_index: int
    orientation: int
    outcome_kind: OutcomeKind
    features: Mapping[str, float]

    def __post_init__(self) -> None:
        if self.orientation not in (-1, 0, 1):
            raise ValueError("orientation must be -1, 0 or 1")
        if self.outcome_kind == "DIRECTIONAL" and self.orientation == 0:
            raise ValueError("directional events require an orientation")
        object.__setattr__(self, "timestamp", _utc(self.timestamp))


def _period(timestamp: datetime) -> str:
    if timestamp < DISCOVERY_END:
        return "DISCOVERY"
    if timestamp < CONFIRMATION_END:
        return "CONFIRMATION"
    return "LOCKED_HOLDOUT"


def _fx_day(timestamp: datetime):
    """Label the DST-aware 17:00 New-York-to-17:00 New-York trading day."""
    local = timestamp.astimezone(ZoneInfo("America/New_York"))
    return local.date() + timedelta(days=1) if local.hour >= 17 else local.date()


def _valid(row: Mapping[str, Any]) -> bool:
    return not (set(row.get("quality_flags") or ()) & INVALID_FLAGS)


def _mid(row: Mapping[str, Any], field: str) -> float:
    return (float(row[f"bid_{field}"]) + float(row[f"ask_{field}"])) / 2.0


def _bar_range(row: Mapping[str, Any]) -> float:
    return (_mid(row, "high") - _mid(row, "low"))


def _quantile(values: Sequence[float], q: float) -> float:
    if not values or not 0 <= q <= 1:
        raise ValueError("quantile requires values and q in [0, 1]")
    ordered = sorted(float(value) for value in values)
    return ordered[round((len(ordered) - 1) * q)]


def _rolling_quantile(values: Sequence[float], window: int, q: float,
                      valid: Sequence[bool] | None = None) -> list[float | None]:
    """Strictly-causal rolling quantile: result[i] uses values[i-window:i]."""
    if valid is None:
        valid = [True] * len(values)
    if len(valid) != len(values):
        raise ValueError("valid mask must match values")
    result: list[float | None] = [None] * len(values)
    ordered: list[float] = []
    for i, value in enumerate(values):
        if i >= window:
            if len(ordered) >= round(window * 0.80):
                result[i] = ordered[round((len(ordered) - 1) * q)]
            if valid[i - window]:
                outgoing = float(values[i - window])
                ordered.pop(bisect_left(ordered, outgoing))
        if valid[i]:
            insort(ordered, float(value))
    return result


def _contiguous(rows: Sequence[Mapping[str, Any]], start: int, end: int) -> bool:
    if start < 0 or end >= len(rows) or start > end:
        return False
    if any(not _valid(rows[i]) for i in range(start, end + 1)):
        return False
    first = _utc(rows[start]["bar_start"])
    last = _utc(rows[end]["bar_start"])
    return (last - first).total_seconds() == (end - start) * M5_SECONDS


def _event(event_id: str, row: Mapping[str, Any], entry_index: int, orientation: int,
           features: Mapping[str, float], *, at_start: bool = False) -> Event:
    definition = EVENT_DEFINITIONS[event_id]
    timestamp = _utc(row["bar_start"] if at_start else row["bar_end"])
    return Event(event_id, timestamp, entry_index, orientation,
                 definition["outcome"], dict(features))


def generate_predeclared_events(rows: Sequence[Mapping[str, Any]]) -> list[Event]:
    """Generate causal M5 events without reading any forward outcome."""
    if not rows:
        return []
    rows = sorted(rows, key=lambda row: _utc(row["bar_start"]))
    ranges = [_bar_range(row) for row in rows]
    ticks = [float(row.get("tick_count", 0)) for row in rows]
    spreads = [float(row.get("spread_pips_p95", 0)) for row in rows]
    valid_mask = [_valid(row) for row in rows]

    range12 = [max(_mid(rows[j], "high") for j in range(max(0, i - 11), i + 1)) -
               min(_mid(rows[j], "low") for j in range(max(0, i - 11), i + 1))
               for i in range(len(rows))]
    range24 = [max(_mid(rows[j], "high") for j in range(max(0, i - 23), i + 1)) -
               min(_mid(rows[j], "low") for j in range(max(0, i - 23), i + 1))
               for i in range(len(rows))]
    range12_median = _rolling_quantile(range12, 288, 0.50, valid_mask)
    range24_median = _rolling_quantile(range24, 288, 0.50, valid_mask)
    tick_q90 = _rolling_quantile(ticks, 288, 0.90, valid_mask)
    spread_median = _rolling_quantile(spreads, 288, 0.50, valid_mask)

    daily: dict[Any, list[float]] = defaultdict(lambda: [float("-inf"), float("inf"), 0])
    for row in rows:
        if not _valid(row):
            continue
        key = _fx_day(_utc(row["bar_start"]))
        daily[key][0] = max(daily[key][0], _mid(row, "high"))
        daily[key][1] = min(daily[key][1], _mid(row, "low"))
        daily[key][2] += 1
    # Exclude partial boundary days and materially incomplete broker-history days.
    completed_days = sorted(key for key, values in daily.items() if values[2] >= 240)

    result: list[Event] = []
    asian_rows: dict[Any, list[int]] = defaultdict(list)
    asian_history: list[float] = []
    active_asian: dict[Any, dict[str, Any]] = {}
    pd_flags: dict[Any, set[str]] = defaultdict(set)
    prior_states = {"compression": False, "trend": False, "mean": False, "micro": False}

    for i, row in enumerate(rows):
        timestamp = _utc(row["bar_start"])
        if not _valid(row):
            prior_states = {key: False for key in prior_states}
            continue
        london = timestamp.astimezone(ZoneInfo("Europe/London"))
        ny = timestamp.astimezone(ZoneInfo("America/New_York"))

        if london.hour == 8 and london.minute == 0:
            result.append(_event("LONDON_OPEN", row, i, 1, {}, at_start=True))
        if ny.hour == 8 and ny.minute == 0:
            result.append(_event("NEW_YORK_OPEN", row, i, 1, {}, at_start=True))

        local_day = timestamp.date()
        minute = timestamp.hour * 60 + timestamp.minute
        if minute < 480:
            asian_rows[local_day].append(i)
        if minute == 480:
            indices = asian_rows.get(local_day, [])
            if len(indices) >= 90 and _contiguous(rows, indices[0], indices[-1]):
                high = max(_mid(rows[j], "high") for j in indices)
                low = min(_mid(rows[j], "low") for j in indices)
                width = high - low
                active_asian[local_day] = {"high": high, "low": low, "high_broken": False, "low_broken": False}
                if len(asian_history) >= 20 and width <= _quantile(asian_history[-20:], 0.25):
                    result.append(_event("ASIAN_RANGE_COMPRESSION", row, i, 0,
                                         {"range_pips": width / PIP_SIZE}, at_start=True))
                asian_history.append(width)
        state = active_asian.get(local_day)
        if state and 480 <= minute < 720 and i + 1 < len(rows):
            if not state["high_broken"] and _mid(row, "high") > state["high"]:
                state["high_broken"] = True
                result.append(_event("ASIAN_HIGH_FIRST_BREAK", row, i + 1, 1,
                                     {"level": state["high"]}))
            if not state["low_broken"] and _mid(row, "low") < state["low"]:
                state["low_broken"] = True
                result.append(_event("ASIAN_LOW_FIRST_BREAK", row, i + 1, -1,
                                     {"level": state["low"]}))

        day = _fx_day(timestamp)
        position = bisect_left(completed_days, day)
        if position > 0 and i + 1 < len(rows):
            previous_day = completed_days[position - 1]
            previous_high, previous_low, _ = daily[previous_day]
            if "HIGH" not in pd_flags[day] and _mid(row, "high") > previous_high:
                pd_flags[day].add("HIGH")
                result.append(_event("PDH_FIRST_BREAK", row, i + 1, 1, {"level": previous_high}))
            if "LOW" not in pd_flags[day] and _mid(row, "low") < previous_low:
                pd_flags[day].add("LOW")
                result.append(_event("PDL_FIRST_BREAK", row, i + 1, -1, {"level": previous_low}))

        if i < 288 or i + 1 >= len(rows) or not _contiguous(rows, i - 23, i):
            continue

        compression = bool(range12_median[i] and range12[i] <= 0.50 * range12_median[i])
        if compression and not prior_states["compression"]:
            result.append(_event("VOLATILITY_COMPRESSION_TRANSITION", row, i + 1, 0,
                                 {"range_ratio": range12[i] / range12_median[i]}))
        prior_states["compression"] = compression

        start6 = _mid(rows[i - 5], "open")
        move6 = _mid(row, "close") - start6
        path6 = sum(abs(_mid(rows[j], "close") - _mid(rows[j], "open")) for j in range(i - 5, i + 1))
        efficiency6 = abs(move6) / path6 if path6 else 0.0
        trend = bool(range12_median[i] and abs(move6) >= range12_median[i] and efficiency6 >= 0.65)
        if trend and not prior_states["trend"]:
            result.append(_event("EFFICIENT_TREND_IMPULSE", row, i + 1, 1 if move6 > 0 else -1,
                                 {"move_pips": abs(move6) / PIP_SIZE, "efficiency": efficiency6}))
        prior_states["trend"] = trend

        closes24 = [_mid(rows[j], "close") for j in range(i - 23, i + 1)]
        centre = mean(closes24)
        deviation = _mid(row, "close") - centre
        low_vol_range = bool(range24_median[i] and range24[i] <= range24_median[i])
        mean_state = bool(low_vol_range and range24[i] > 0 and abs(deviation) >= 0.30 * range24[i])
        if mean_state and not prior_states["mean"]:
            result.append(_event("RANGE_DEVIATION_MEAN_REVERSION", row, i + 1,
                                 -1 if deviation > 0 else 1,
                                 {"deviation_pips": abs(deviation) / PIP_SIZE,
                                  "range_pips": range24[i] / PIP_SIZE}))
        prior_states["mean"] = mean_state

        bar_move = _mid(row, "close") - _mid(row, "open")
        efficiency = abs(bar_move) / ranges[i] if ranges[i] else 0.0
        micro = bool(tick_q90[i] is not None and spread_median[i] is not None and
                     ticks[i] >= tick_q90[i] and spreads[i] <= spread_median[i] and
                     efficiency >= 0.70 and bar_move != 0)
        if micro and not prior_states["micro"]:
            result.append(_event("HIGH_INTENSITY_COHERENT_BAR_PROXY", row, i + 1,
                                 1 if bar_move > 0 else -1,
                                 {"tick_count": ticks[i], "efficiency": efficiency,
                                  "spread_p95": spreads[i]}))
        prior_states["micro"] = micro

    return sorted(result, key=lambda event: (event.timestamp, event.event_id))


def _summary(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ci = block_bootstrap_expectancy_ci(values, block_size=min(5, len(values)), samples=500)
    return {"n": len(values), "mean_pips": mean(values), "median_pips": median(values),
            "ci_95": asdict(ci)}


def summarize_events(rows: Sequence[Mapping[str, Any]], events: Iterable[Event]) -> dict[str, Any]:
    rows = sorted(rows, key=lambda row: _utc(row["bar_start"]))
    events = list(events)
    values: dict[str, dict[str, dict[str, dict[str, list[float]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
    locked_counts: dict[str, int] = defaultdict(int)

    for event in events:
        period = _period(event.timestamp)
        if period == "LOCKED_HOLDOUT":
            # Governance firewall: do not inspect entry or future price fields.
            locked_counts[event.event_id] += 1
            continue
        for horizon in HORIZONS:
            exit_index = event.entry_index + horizon - 1
            if not _contiguous(rows, event.entry_index, exit_index):
                continue
            entry = rows[event.entry_index]
            future = rows[exit_index]
            mid_move = (_mid(future, "close") - _mid(entry, "open")) / PIP_SIZE
            if event.outcome_kind == "MAGNITUDE":
                values[event.event_id][period][str(horizon)]["primary"].append(abs(mid_move))
            else:
                gross = event.orientation * mid_move
                executable = ((float(future["bid_close"]) - float(entry["ask_open"])) / PIP_SIZE
                              if event.orientation > 0 else
                              (float(entry["bid_open"]) - float(future["ask_close"])) / PIP_SIZE)
                values[event.event_id][period][str(horizon)]["primary"].append(gross)
                values[event.event_id][period][str(horizon)]["executable"].append(executable)

    output: dict[str, Any] = {}
    event_ids = sorted({event.event_id for event in events})
    for event_id in event_ids:
        outcome_kind = EVENT_DEFINITIONS[event_id]["outcome"]
        event_output: dict[str, Any] = {"definition": EVENT_DEFINITIONS[event_id], "periods": {}}
        for period in ("DISCOVERY", "CONFIRMATION"):
            horizons: dict[str, Any] = {}
            for horizon, metrics in values[event_id][period].items():
                record = {"outcome_kind": outcome_kind, **_summary(metrics["primary"])}
                if metrics.get("executable"):
                    record["executable"] = _summary(metrics["executable"])
                horizons[horizon] = record
            event_output["periods"][period] = horizons
        event_output["periods"]["LOCKED_HOLDOUT"] = {
            "event_count": locked_counts[event_id], "outcomes_computed": False,
        }
        output[event_id] = event_output
    return output


def run_event_studies_from_dataset(dataset: BarDataset, output_dir: str | Path) -> Path:
    bars = dataset.bars["M5"]
    events = generate_predeclared_events(bars)
    output = {
        "schema_version": "event-studies/v2",
        "research_mode": "NON_EXECUTABLE_EVENT_STUDY",
        "automatic_promotion": False,
        "dataset": dataset.manifest,
        "boundaries": {
            "discovery_end": DISCOVERY_END.isoformat(),
            "confirmation_end": CONFIRMATION_END.isoformat(),
            "holdout_status": "LOCKED",
            "holdout_outcomes_computed": False,
        },
        "event_count": len(events),
        "events": summarize_events(bars, events),
    }
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "event_studies.json").write_text(
        json.dumps(output, indent=2, default=str, sort_keys=True), encoding="utf-8")
    return root


def run_predeclared_event_studies(bars_dir: str | Path, output_dir: str | Path) -> Path:
    return run_event_studies_from_dataset(BarDataset.load(bars_dir), output_dir)


def run_session_open_studies(bars_dir: str | Path, output_dir: str | Path) -> Path:
    """Compatibility alias for the original CLI/API name."""
    return run_predeclared_event_studies(bars_dir, output_dir)
