"""Fold-local feature normalisation for leakage-safe walk-forward research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from analytics.microstructure.tick_state_classifier import SessionRobustBaseline
from .walk_forward import EventInterval, WalkForwardSplit, purged_walk_forward_splits


@dataclass(frozen=True, slots=True)
class BaselineEvent:
    interval: EventInterval
    session_key: str
    features: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class FoldBaseline:
    split: WalkForwardSplit
    baseline: SessionRobustBaseline
    fitted_indices: tuple[int, ...]


def fit_walk_forward_session_baselines(
    events: Sequence[BaselineEvent], *, minimum_train_size: int, validation_size: int,
    embargo: timedelta, step_size: int | None = None,
) -> list[FoldBaseline]:
    """Fit a new baseline per split from purged historical training events only."""
    intervals = [event.interval for event in events]
    splits = purged_walk_forward_splits(
        intervals, minimum_train_size=minimum_train_size, validation_size=validation_size,
        embargo=embargo, step_size=step_size,
    )
    result: list[FoldBaseline] = []
    for split in splits:
        baseline = SessionRobustBaseline()
        baseline.fit([events[i].features for i in split.train_indices], [events[i].session_key for i in split.train_indices])
        result.append(FoldBaseline(split, baseline, split.train_indices))
    return result
