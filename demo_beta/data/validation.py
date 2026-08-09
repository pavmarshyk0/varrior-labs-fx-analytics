from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from statistics import median
from typing import Sequence

from ..contracts import Tick, TickQualityReport


class DataQualityViolation(ValueError):
    pass


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    weight = pos - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


@dataclass(frozen=True, slots=True)
class TickFeedValidator:
    pip_size: float = 0.0001
    expected_interval_ms: int | None = None
    gap_threshold_ms: int | None = None

    def validate(self, ticks: Sequence[Tick]) -> TickQualityReport:
        if not ticks:
            return TickQualityReport(
                tick_count=0,
                valid=False,
                timestamp_monotonic=True,
                out_of_order_count=0,
                equal_timestamp_count=0,
                duplicate_tick_count=0,
                duplicate_tick_ratio=0.0,
                crossed_quote_count=0,
                nonpositive_quote_count=0,
                gap_count=0,
                missing_tick_ratio=None,
                spread_median_pips=None,
                spread_p95_pips=None,
                hard_failures=("EMPTY_FEED",),
            )

        out_of_order = 0
        equal_timestamp = 0
        gaps = 0
        inferred_missing = 0
        prior_time: int | None = None
        for tick in ticks:
            if prior_time is not None:
                delta = tick.time_msc - prior_time
                if delta < 0:
                    out_of_order += 1
                elif delta == 0:
                    equal_timestamp += 1
                if self.gap_threshold_ms is not None and delta > self.gap_threshold_ms:
                    gaps += 1
                if self.expected_interval_ms is not None and delta > self.expected_interval_ms:
                    inferred_missing += max(0, ceil(delta / self.expected_interval_ms) - 1)
            prior_time = tick.time_msc

        identities = [(t.time_msc, t.bid, t.ask, t.flags) for t in ticks]
        duplicate_count = len(identities) - len(set(identities))
        crossed = sum(t.bid > t.ask for t in ticks)
        nonpositive = sum(t.bid <= 0 or t.ask <= 0 for t in ticks)
        spreads_pips = [t.spread / self.pip_size for t in ticks if t.bid > 0 and t.ask >= t.bid]

        failures: list[str] = []
        if out_of_order:
            failures.append("OUT_OF_ORDER_TICKS")
        if crossed:
            failures.append("CROSSED_QUOTES")
        if nonpositive:
            failures.append("NONPOSITIVE_QUOTES")

        missing_ratio: float | None = None
        if self.expected_interval_ms is not None:
            expected_total = len(ticks) + inferred_missing
            missing_ratio = inferred_missing / expected_total if expected_total else 0.0

        return TickQualityReport(
            tick_count=len(ticks),
            valid=not failures,
            timestamp_monotonic=out_of_order == 0,
            out_of_order_count=out_of_order,
            equal_timestamp_count=equal_timestamp,
            duplicate_tick_count=duplicate_count,
            duplicate_tick_ratio=duplicate_count / len(ticks),
            crossed_quote_count=crossed,
            nonpositive_quote_count=nonpositive,
            gap_count=gaps,
            missing_tick_ratio=missing_ratio,
            spread_median_pips=median(spreads_pips) if spreads_pips else None,
            spread_p95_pips=_percentile(spreads_pips, 0.95),
            hard_failures=tuple(failures),
        )
