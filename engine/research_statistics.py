"""Deterministic OOS trading statistics; all returns are net executable R."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from math import sqrt
from typing import Sequence


@dataclass(frozen=True, slots=True)
class TradeObservation:
    timestamp: datetime
    net_r: float
    mae_r: float
    mfe_r: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("trade timestamp must be timezone-aware")
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class PerformanceStatistics:
    trade_count: int
    expectancy_r: float | None
    win_rate: float | None
    average_mae_r: float | None
    average_mfe_r: float | None
    maximum_drawdown_r: float | None
    longest_losing_streak: int
    frequency_per_week: float | None


def performance_statistics(trades: Sequence[TradeObservation]) -> PerformanceStatistics:
    if not trades:
        return PerformanceStatistics(0, None, None, None, None, None, 0, None)
    ordered = sorted(trades, key=lambda trade: trade.timestamp)
    returns = [trade.net_r for trade in ordered]
    equity = peak = 0.0
    max_drawdown = 0.0
    streak = longest = 0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        streak = streak + 1 if value < 0 else 0
        longest = max(longest, streak)
    elapsed_weeks = (ordered[-1].timestamp - ordered[0].timestamp).total_seconds() / (7 * 24 * 3600)
    return PerformanceStatistics(
        trade_count=len(ordered), expectancy_r=sum(returns) / len(returns),
        win_rate=sum(value > 0 for value in returns) / len(returns),
        average_mae_r=sum(trade.mae_r for trade in ordered) / len(ordered),
        average_mfe_r=sum(trade.mfe_r for trade in ordered) / len(ordered),
        maximum_drawdown_r=max_drawdown, longest_losing_streak=longest,
        frequency_per_week=(len(ordered) / elapsed_weeks) if elapsed_weeks > 0 else None,
    )


@dataclass(frozen=True, slots=True)
class BootstrapCI:
    point_estimate: float
    lower_95: float
    upper_95: float
    samples: int
    block_size: int


@dataclass(frozen=True, slots=True)
class TargetHitStatistics:
    sample_size: int
    probabilities_before_stop: dict[float, float]
    ambiguous_count: int


def target_before_stop_probabilities(paths: Sequence[Sequence[float]], *, targets_r: Sequence[float] =
                                     (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)) -> TargetHitStatistics:
    """Path-aware target-hit probabilities in R.

    Each path is ordered realised excursion values.  A target only counts when
    it appears before the first <= -1R stop observation; unordered OHLC/MFE is
    deliberately not treated as a winner.
    """
    if not paths or any(target <= 0 for target in targets_r):
        raise ValueError("non-empty paths and positive targets are required")
    hits = {float(target): 0 for target in targets_r}
    ambiguous = 0
    for path in paths:
        if not path:
            ambiguous += 1
            continue
        for target in hits:
            target_at = next((i for i, value in enumerate(path) if value >= target), None)
            stop_at = next((i for i, value in enumerate(path) if value <= -1.0), None)
            if target_at is not None and (stop_at is None or target_at < stop_at):
                hits[target] += 1
    return TargetHitStatistics(len(paths), {target: count / len(paths) for target, count in hits.items()}, ambiguous)


def block_bootstrap_expectancy_ci(returns: Sequence[float], *, block_size: int, samples: int = 2_000,
                                  seed: int = 0) -> BootstrapCI:
    """Circular moving-block bootstrap for serially dependent trade returns."""
    if not returns or block_size < 1 or samples < 1:
        raise ValueError("returns, positive block_size and positive samples are required")
    values = [float(value) for value in returns]
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(samples):
        resampled: list[float] = []
        while len(resampled) < len(values):
            start = rng.randrange(len(values))
            resampled.extend(values[(start + offset) % len(values)] for offset in range(block_size))
        estimates.append(sum(resampled[:len(values)]) / len(values))
    estimates.sort()
    def quantile(q: float) -> float:
        index = round((len(estimates) - 1) * q)
        return estimates[index]
    return BootstrapCI(sum(values) / len(values), quantile(0.025), quantile(0.975), samples, block_size)
