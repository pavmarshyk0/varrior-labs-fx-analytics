"""DST-aware event-time hazard engine with hierarchical posterior shrinkage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from statistics import mean, stdev
from typing import Sequence

from demo_beta.analytics.contracts import DecisionEffect, ModelStatus, ModuleOutput
from demo_beta.contracts import Candidate

from demo_beta.analytics.context.event_time_hazard import (  # noqa: F401
    BenchmarkWindowRegistry,
    BenchmarkWindowState,
    CalendarLeakageError,
    CalendarSnapshot,
    EconomicCalendarAdapter,
    Impact,
    MacroEvent,
    MarketClock,
    MarketClockState,
    ScheduledMacroJumpGuard,
)


@dataclass(frozen=True, slots=True)
class TemporalContext:
    session: str
    benchmark: str
    dst_state: str
    regime: str

    @property
    def bucket_key(self) -> tuple[str, str, str, str]:
        return (self.session, self.benchmark, self.dst_state, self.regime)

    @property
    def parent_key(self) -> tuple[str, str]:
        return (self.session, self.regime)


@dataclass(frozen=True, slots=True)
class HistoricalTemporalOutcome:
    timestamp: datetime
    context: TemporalContext
    net_r: float


@dataclass(frozen=True, slots=True)
class PosteriorEstimate:
    mean_r: float
    lower_95_r: float
    upper_95_r: float
    raw_sample_size: int
    parent_sample_size: int
    shrinkage_weight: float
    independently_actionable: bool


class TemporalPosteriorTable:
    """Hierarchical empirical-Bayes-like shrinkage for sparse time buckets.

    This is context estimation, not a direction generator. Small buckets shrink
    to session/regime parents and cannot independently drive a trade.
    """

    def __init__(self, prior_strength: float = 30.0, minimum_bucket_size: int = 30) -> None:
        if prior_strength <= 0 or minimum_bucket_size < 1:
            raise ValueError("invalid posterior-table parameters")
        self.prior_strength = prior_strength
        self.minimum_bucket_size = minimum_bucket_size
        self._bucket: dict[tuple[str, str, str, str], list[float]] = {}
        self._parent: dict[tuple[str, str], list[float]] = {}
        self._global: list[float] = []

    def fit(self, outcomes: Sequence[HistoricalTemporalOutcome]) -> None:
        self._bucket.clear()
        self._parent.clear()
        self._global = []
        for item in outcomes:
            value = float(item.net_r)
            self._bucket.setdefault(item.context.bucket_key, []).append(value)
            self._parent.setdefault(item.context.parent_key, []).append(value)
            self._global.append(value)

    @staticmethod
    def _mean(values: Sequence[float], fallback: float) -> float:
        return mean(values) if values else fallback

    def query(self, context: TemporalContext) -> PosteriorEstimate:
        if not self._global:
            raise RuntimeError("temporal posterior table is not fitted")
        global_mean = mean(self._global)
        parent = self._parent.get(context.parent_key, [])
        bucket = self._bucket.get(context.bucket_key, [])
        parent_mean = self._mean(parent, global_mean)
        weight = len(bucket) / (len(bucket) + self.prior_strength)
        shrunk_mean = weight * self._mean(bucket, parent_mean) + (1.0 - weight) * parent_mean

        # Uncertainty is deliberately conservative for sparse buckets: use the
        # parent dispersion when the local bucket does not have two observations.
        dispersion_source = bucket if len(bucket) >= 2 else parent if len(parent) >= 2 else self._global
        dispersion = stdev(dispersion_source) if len(dispersion_source) >= 2 else 0.0
        effective_n = max(1.0, len(bucket) * weight + len(parent) * (1.0 - weight))
        half_width = 1.96 * dispersion / sqrt(effective_n)
        return PosteriorEstimate(
            mean_r=shrunk_mean,
            lower_95_r=shrunk_mean - half_width,
            upper_95_r=shrunk_mean + half_width,
            raw_sample_size=len(bucket),
            parent_sample_size=len(parent),
            shrinkage_weight=weight,
            independently_actionable=len(bucket) >= self.minimum_bucket_size,
        )


@dataclass(slots=True)
class EventTimeHazardModule:
    posterior_table: TemporalPosteriorTable | None = None
    prospective_directional_approval: bool = False
    version: str = "0.1.0"

    def evaluate(self, candidate: Candidate, context: TemporalContext) -> ModuleOutput:
        estimate = self.posterior_table.query(context) if self.posterior_table is not None else None
        signal = 0.0
        effect = DecisionEffect.NEUTRAL
        evidence: tuple[str, ...] = ()
        if (
            estimate is not None
            and self.prospective_directional_approval
            and estimate.independently_actionable
            and estimate.upper_95_r < 0.0
        ):
            # Only a pre-approved, sufficiently populated adverse time bucket
            # may become a soft veto. It still cannot invert candidate direction.
            signal = -min(1.0, abs(estimate.mean_r))
            effect = DecisionEffect.SOFT_VETO
            evidence = ("PROSPECTIVE_ADVERSE_TIME_BUCKET",)
        features = {
            "session": context.session,
            "benchmark": context.benchmark,
            "dst_state": context.dst_state,
            "regime": context.regime,
        }
        if estimate is not None:
            features.update(
                {
                    "posterior_mean_r": estimate.mean_r,
                    "posterior_lower_95_r": estimate.lower_95_r,
                    "posterior_upper_95_r": estimate.upper_95_r,
                    "posterior_bucket_n": estimate.raw_sample_size,
                    "posterior_parent_n": estimate.parent_sample_size,
                    "posterior_shrinkage_weight": estimate.shrinkage_weight,
                }
            )
        return ModuleOutput(
            module="event_time_hazard",
            version=self.version,
            candidate_id=candidate.candidate_id,
            direction=candidate.direction,
            signal=signal,
            confidence=1.0 if estimate and estimate.independently_actionable else 0.0,
            valid=True,
            decision_effect=effect,
            event="TEMPORAL_CONTEXT",
            generated_at=candidate.entry_available_at,
            timeframe=candidate.timeframe,
            features=features,
            evidence=evidence,
            research_reliability={
                "evidence_grade": "B",
                "model_status": ModelStatus.RESEARCH.value,
                "prospective_directional_approval": self.prospective_directional_approval,
            },
        )

__all__ = [
    "BenchmarkWindowRegistry",
    "BenchmarkWindowState",
    "CalendarLeakageError",
    "CalendarSnapshot",
    "EconomicCalendarAdapter",
    "Impact",
    "MacroEvent",
    "MarketClock",
    "MarketClockState",
    "ScheduledMacroJumpGuard",
    "TemporalContext",
    "HistoricalTemporalOutcome",
    "PosteriorEstimate",
    "TemporalPosteriorTable",
    "EventTimeHazardModule",
]
