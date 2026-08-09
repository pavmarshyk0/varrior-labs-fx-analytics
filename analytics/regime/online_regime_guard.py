"""Online volatility/liquidity changepoint guard.

BOCPD is intentionally SHADOW by default. Its suggested multiplier is logged,
while the applied multiplier remains 1.0 until prospective promotion.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from math import exp, lgamma, log, pi
from statistics import median
from typing import Sequence


def _mad(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    center = median(values)
    return median(abs(v - center) for v in values)


@dataclass(frozen=True, slots=True)
class M5Observation:
    timestamp: datetime
    realized_volatility_5m: float
    realized_volatility_30m: float
    median_spread_pips_5m: float
    spread_p95_pips_5m: float
    tick_intensity_5m: float
    absolute_return_5m: float
    missing_tick_ratio: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))
        values = self.raw_vector()
        if any(value < 0 for value in values):
            raise ValueError("regime observation values cannot be negative")
        if not 0.0 <= self.missing_tick_ratio <= 1.0:
            raise ValueError("missing_tick_ratio must be within [0, 1]")

    def raw_vector(self) -> tuple[float, ...]:
        return (
            self.realized_volatility_5m,
            self.realized_volatility_30m,
            self.median_spread_pips_5m,
            self.spread_p95_pips_5m,
            self.tick_intensity_5m,
            self.absolute_return_5m,
        )

    def log_vector(self) -> tuple[float, ...]:
        eps = 1e-12
        return tuple(log(value + eps) for value in self.raw_vector())


class OnlineRobustScaler:
    def __init__(self, max_history: int = 2_016, min_history: int = 30) -> None:
        if max_history < min_history or min_history < 1:
            raise ValueError("invalid robust-scaler history limits")
        self.max_history = max_history
        self.min_history = min_history
        self._rows: deque[tuple[float, ...]] = deque(maxlen=max_history)

    @property
    def sample_size(self) -> int:
        return len(self._rows)

    @property
    def ready(self) -> bool:
        return self.sample_size >= self.min_history

    def update(self, observation: Sequence[float]) -> None:
        row = tuple(float(v) for v in observation)
        if self._rows and len(row) != len(self._rows[0]):
            raise ValueError("observation dimension changed")
        self._rows.append(row)

    def transform(self, observation: Sequence[float]) -> tuple[float, ...]:
        row = tuple(float(v) for v in observation)
        if not self._rows:
            return tuple(0.0 for _ in row)
        columns = list(zip(*self._rows))
        if len(columns) != len(row):
            raise ValueError("observation dimension changed")
        output = []
        for value, column in zip(row, columns):
            center = median(column)
            scale = max(1.4826 * _mad(column), 1e-6)
            output.append((value - center) / scale)
        return tuple(output)


@dataclass(frozen=True, slots=True)
class RobustThresholdState:
    unstable: bool
    volatility_z: float
    spread_z: float


class RobustThresholdRegimeBaseline:
    """Simple rolling median/MAD comparator BOCPD must beat in OOS ablation."""

    def __init__(self, history: int = 288, threshold: float = 3.0, min_history: int = 30) -> None:
        self.history = history
        self.threshold = threshold
        self.min_history = min_history
        self._volatility: deque[float] = deque(maxlen=history)
        self._spread: deque[float] = deque(maxlen=history)

    @staticmethod
    def _z(value: float, history: Sequence[float]) -> float:
        if len(history) < 2:
            return 0.0
        center = median(history)
        scale = max(1.4826 * _mad(history), 1e-9)
        return (value - center) / scale

    def update(self, observation: M5Observation) -> RobustThresholdState:
        vol_z = self._z(observation.realized_volatility_5m, tuple(self._volatility))
        spread_z = self._z(observation.median_spread_pips_5m, tuple(self._spread))
        ready = len(self._volatility) >= self.min_history
        state = RobustThresholdState(ready and max(vol_z, spread_z) >= self.threshold, vol_z, spread_z)
        self._volatility.append(observation.realized_volatility_5m)
        self._spread.append(observation.median_spread_pips_5m)
        return state


@dataclass(frozen=True, slots=True)
class RunStats:
    n: int
    mean: tuple[float, ...]
    m2: tuple[float, ...]

    @classmethod
    def empty(cls, dimension: int) -> "RunStats":
        return cls(0, (0.0,) * dimension, (0.0,) * dimension)

    def update(self, observation: Sequence[float]) -> "RunStats":
        x = tuple(float(v) for v in observation)
        if len(x) != len(self.mean):
            raise ValueError("observation dimension changed")
        n = self.n + 1
        means: list[float] = []
        m2s: list[float] = []
        for value, old_mean, old_m2 in zip(x, self.mean, self.m2):
            delta = value - old_mean
            new_mean = old_mean + delta / n
            means.append(new_mean)
            m2s.append(old_m2 + delta * (value - new_mean))
        return RunStats(n, tuple(means), tuple(m2s))


@dataclass(frozen=True, slots=True)
class StudentTPredictiveModel:
    prior_scale: float = 2.5
    prior_df: float = 4.0

    def predictive_logpdf(self, observation: Sequence[float], stats: RunStats) -> float:
        total = 0.0
        for value, mean, m2 in zip(observation, stats.mean, stats.m2):
            variance = m2 / max(1, stats.n - 1) if stats.n > 1 else self.prior_scale**2
            scale = max(variance**0.5, 0.25)
            nu = max(self.prior_df, self.prior_df + stats.n - 1)
            z2 = ((float(value) - mean) / scale) ** 2
            total += (
                lgamma((nu + 1.0) / 2.0)
                - lgamma(nu / 2.0)
                - 0.5 * log(nu * pi)
                - log(scale)
                - ((nu + 1.0) / 2.0) * log(1.0 + z2 / nu)
            )
        return total


@dataclass(frozen=True, slots=True)
class BOCPDState:
    change_probability: float
    expected_run_length_bars: float
    posterior: tuple[float, ...]


class BOCPD:
    def __init__(self, dimension: int, hazard_mean: float = 144.0, max_run_length: int = 288) -> None:
        if dimension < 1 or hazard_mean <= 1 or max_run_length < 2:
            raise ValueError("invalid BOCPD parameters")
        self.dimension = dimension
        self.hazard = 1.0 / hazard_mean
        self.max_run_length = max_run_length
        self.model = StudentTPredictiveModel()
        self.posterior: list[float] = [1.0]
        self.stats: list[RunStats] = [RunStats.empty(dimension)]

    def update(self, observation: Sequence[float]) -> BOCPDState:
        x = tuple(float(v) for v in observation)
        if len(x) != self.dimension:
            raise ValueError("observation dimension changed")
        run_logp = [self.model.predictive_logpdf(x, stats) for stats in self.stats]
        prior_logp = self.model.predictive_logpdf(x, RunStats.empty(self.dimension))
        anchor = max(run_logp + [prior_logp])
        run_likelihood = [exp(value - anchor) for value in run_logp]
        prior_likelihood = exp(prior_logp - anchor)

        cp_weight = self.hazard * prior_likelihood * sum(self.posterior)
        growth = [
            (1.0 - self.hazard) * probability * likelihood
            for probability, likelihood in zip(self.posterior, run_likelihood)
        ]
        weights = [cp_weight, *growth]
        total = sum(weights)
        normalized = [weight / total for weight in weights]
        new_stats = [RunStats.empty(self.dimension).update(x)] + [stats.update(x) for stats in self.stats]
        if len(normalized) > self.max_run_length + 1:
            normalized = normalized[: self.max_run_length + 1]
            new_stats = new_stats[: self.max_run_length + 1]
            norm = sum(normalized)
            normalized = [value / norm for value in normalized]
        self.posterior = normalized
        self.stats = new_stats
        expected = sum(run_length * probability for run_length, probability in enumerate(normalized))
        return BOCPDState(normalized[0], expected, tuple(normalized))


@dataclass(frozen=True, slots=True)
class RegimeDecision:
    event: str
    valid: bool
    suggested_risk_multiplier: float
    applied_risk_multiplier: float
    hard_veto: bool


@dataclass(frozen=True, slots=True)
class RegimePolicy:
    change_threshold: float = 0.55
    severe_missing_ratio: float = 0.02
    mode: str = "SHADOW"

    def decide(self, state: BOCPDState, data_quality_valid: bool) -> RegimeDecision:
        if not data_quality_valid:
            return RegimeDecision("DATA_QUALITY_INVALID", False, 0.0, 0.0, True)
        unstable = state.change_probability >= self.change_threshold
        suggested = 0.5 if unstable else 1.0
        if self.mode == "SHADOW":
            return RegimeDecision(
                "VOLATILITY_LIQUIDITY_CHANGEPOINT" if unstable else "REGIME_STABLE",
                True,
                suggested,
                1.0,
                False,
            )
        return RegimeDecision(
            "VOLATILITY_LIQUIDITY_CHANGEPOINT" if unstable else "REGIME_STABLE",
            not unstable,
            suggested,
            suggested,
            False,
        )


@dataclass(frozen=True, slots=True)
class RegimeOutput:
    module: str
    version: str
    generated_at: datetime
    signal: float
    confidence: float
    valid: bool
    event: str
    change_probability: float
    expected_run_length_bars: float
    suggested_risk_multiplier: float
    applied_risk_multiplier: float
    model_status: str


class OnlineRegimeGuard:
    def __init__(
        self,
        scaler: OnlineRobustScaler | None = None,
        bocpd: BOCPD | None = None,
        policy: RegimePolicy | None = None,
    ) -> None:
        self.scaler = scaler or OnlineRobustScaler()
        self.bocpd = bocpd or BOCPD(dimension=6)
        self.policy = policy or RegimePolicy(mode="SHADOW")

    def evaluate(self, observation: M5Observation) -> RegimeOutput:
        raw = observation.log_vector()
        scaled = self.scaler.transform(raw)
        data_quality_valid = observation.missing_tick_ratio <= self.policy.severe_missing_ratio
        if not self.scaler.ready:
            self.scaler.update(raw)
            return RegimeOutput(
                module="online_regime_guard",
                version="0.1.0",
                generated_at=observation.timestamp,
                signal=0.0,
                confidence=0.0,
                valid=data_quality_valid,
                event="WARMUP",
                change_probability=0.0,
                expected_run_length_bars=0.0,
                suggested_risk_multiplier=1.0,
                applied_risk_multiplier=1.0 if data_quality_valid else 0.0,
                model_status="SHADOW",
            )
        state = self.bocpd.update(scaled)
        decision = self.policy.decide(state, data_quality_valid)
        self.scaler.update(raw)
        concentration = max(state.posterior, default=0.0)
        return RegimeOutput(
            module="online_regime_guard",
            version="0.1.0",
            generated_at=observation.timestamp,
            signal=1.0 - 2.0 * state.change_probability,
            confidence=concentration,
            valid=decision.valid,
            event=decision.event,
            change_probability=state.change_probability,
            expected_run_length_bars=state.expected_run_length_bars,
            suggested_risk_multiplier=decision.suggested_risk_multiplier,
            applied_risk_multiplier=decision.applied_risk_multiplier,
            model_status=self.policy.mode,
        )
