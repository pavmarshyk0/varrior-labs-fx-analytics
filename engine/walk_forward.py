"""Chronological purged walk-forward splits for overlapping event labels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Sequence


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("event times must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class EventInterval:
    start: datetime
    label_end: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _utc(self.start))
        object.__setattr__(self, "label_end", _utc(self.label_end))
        if self.label_end < self.start:
            raise ValueError("label_end cannot precede event start")


@dataclass(frozen=True, slots=True)
class WalkForwardSplit:
    train_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    validation_start: datetime
    validation_end: datetime


@dataclass(frozen=True, slots=True)
class LockedFinalHoldout:
    """Explicit holdout boundary, intentionally excluded from all tuning folds."""
    indices: tuple[int, ...]
    start: datetime
    end: datetime


def lock_final_holdout(events: Sequence[EventInterval], *, holdout_size: int) -> LockedFinalHoldout:
    if holdout_size < 1 or holdout_size >= len(events):
        raise ValueError("holdout_size must be in [1, len(events))")
    if any(events[i].start > events[i + 1].start for i in range(len(events) - 1)):
        raise ValueError("events must be sorted chronologically")
    indices = tuple(range(len(events) - holdout_size, len(events)))
    return LockedFinalHoldout(indices, events[indices[0]].start, max(events[i].label_end for i in indices))


def purged_walk_forward_splits(
    events: Sequence[EventInterval],
    *,
    minimum_train_size: int,
    validation_size: int,
    embargo: timedelta,
    step_size: int | None = None,
) -> list[WalkForwardSplit]:
    if minimum_train_size < 1 or validation_size < 1 or embargo < timedelta(0):
        raise ValueError("invalid walk-forward parameters")
    if any(events[i].start > events[i + 1].start for i in range(len(events) - 1)):
        raise ValueError("events must be sorted chronologically")
    step = step_size or validation_size
    if step < 1:
        raise ValueError("step_size must be positive")
    splits: list[WalkForwardSplit] = []
    validation_start_idx = minimum_train_size
    while validation_start_idx < len(events):
        validation_end_idx = min(len(events), validation_start_idx + validation_size)
        valid_indices = tuple(range(validation_start_idx, validation_end_idx))
        if not valid_indices:
            break
        valid_start = events[valid_indices[0]].start
        valid_end = max(events[i].label_end for i in valid_indices)
        cutoff = valid_start - embargo
        train_indices = tuple(
            i for i in range(validation_start_idx) if events[i].label_end < cutoff
        )
        if len(train_indices) >= minimum_train_size:
            splits.append(WalkForwardSplit(train_indices, valid_indices, valid_start, valid_end))
        validation_start_idx += step
    return splits
