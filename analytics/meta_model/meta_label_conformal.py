"""Deterministic meta-label + conformal abstention infrastructure.

The module enforces the research rule that meta-learning is not trained before
a meaningful candidate sample exists. Callers must fit it inside purged
walk-forward training folds; random splitting is intentionally absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from statistics import median
from typing import Sequence

from demo_beta.backtesting.executable import ExecutableBidAskBacktester
from demo_beta.contracts import BacktestResult, Candidate, Tick


class InsufficientSampleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TripleBarrierLabel:
    candidate_id: str
    label: int | None
    result: BacktestResult


class TripleBarrierLabeler:
    """Bridge to the executable bid/ask simulator used for meta labels."""

    def __init__(self, backtester: ExecutableBidAskBacktester | None = None) -> None:
        self.backtester = backtester or ExecutableBidAskBacktester()

    def label(self, candidate: Candidate, ticks: Sequence[Tick]) -> TripleBarrierLabel:
        result = self.backtester.simulate(candidate, ticks)
        return TripleBarrierLabel(candidate.candidate_id, result.label, result)


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("quantile requires observations")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * q + 0.999999)))
    return ordered[index]


class _RobustScaler:
    def fit(self, x: Sequence[Sequence[float]]) -> None:
        if not x:
            raise ValueError("empty feature matrix")
        columns = list(zip(*x))
        self.center = tuple(median(column) for column in columns)
        self.scale = tuple(
            max(1e-9, 1.4826 * median(abs(v - c) for v in column))
            for column, c in zip(columns, self.center)
        )

    def transform_one(self, row: Sequence[float]) -> tuple[float, ...]:
        if len(row) != len(self.center):
            raise ValueError("feature dimension changed")
        return tuple((float(v) - c) / s for v, c, s in zip(row, self.center, self.scale))


class _LogisticModel:
    def fit(self, x: Sequence[Sequence[float]], y: Sequence[int], l2: float = 0.01, iterations: int = 400) -> None:
        if len(x) != len(y) or not x:
            raise ValueError("invalid training data")
        if len(set(y)) < 2:
            raise ValueError("meta-label training requires both positive and negative labels")
        dimension = len(x[0])
        self.weights = [0.0] * (dimension + 1)
        n = float(len(x))
        for step in range(iterations):
            gradient = [0.0] * len(self.weights)
            for row, target in zip(x, y):
                score = self.weights[0] + sum(w * value for w, value in zip(self.weights[1:], row))
                probability = 1.0 / (1.0 + exp(-max(-35.0, min(35.0, score))))
                error = probability - target
                gradient[0] += error
                for i, value in enumerate(row, start=1):
                    gradient[i] += error * value
            rate = 0.15 / (1.0 + step / 80.0)
            self.weights[0] -= rate * gradient[0] / n
            for i in range(1, len(self.weights)):
                self.weights[i] -= rate * (gradient[i] / n + l2 * self.weights[i])

    def predict_probability(self, row: Sequence[float]) -> float:
        score = self.weights[0] + sum(w * value for w, value in zip(self.weights[1:], row))
        return 1.0 / (1.0 + exp(-max(-35.0, min(35.0, score))))


@dataclass(frozen=True, slots=True)
class ConformalPrediction:
    probability: float
    prediction_set: frozenset[int]

    @property
    def abstain(self) -> bool:
        return len(self.prediction_set) != 1


class AdaptiveConformalGate:
    def __init__(self, alpha: float = 0.10) -> None:
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be within (0, 1)")
        self.alpha = alpha
        self.threshold: float | None = None

    def fit(self, probabilities: Sequence[float], outcomes: Sequence[int]) -> None:
        if len(probabilities) != len(outcomes) or not probabilities:
            raise ValueError("invalid calibration data")
        scores = [1.0 - (p if y == 1 else 1.0 - p) for p, y in zip(probabilities, outcomes)]
        self.threshold = _quantile(scores, 1.0 - self.alpha)

    def predict(self, probability: float) -> ConformalPrediction:
        if self.threshold is None:
            raise RuntimeError("conformal gate is not fitted")
        labels: set[int] = set()
        if 1.0 - probability <= self.threshold:
            labels.add(1)
        if probability <= self.threshold:
            labels.add(0)
        return ConformalPrediction(probability, frozenset(labels))


class MetaLabelConformal:
    """Small deterministic research baseline; not enabled in the trading path."""

    def __init__(self, minimum_candidates: int = 800, alpha: float = 0.10) -> None:
        self.minimum_candidates = minimum_candidates
        self.scaler = _RobustScaler()
        self.model = _LogisticModel()
        self.conformal = AdaptiveConformalGate(alpha)
        self._fitted = False

    def fit(
        self,
        train_x: Sequence[Sequence[float]],
        train_y: Sequence[int],
        calibration_x: Sequence[Sequence[float]],
        calibration_y: Sequence[int],
    ) -> None:
        total = len(train_x) + len(calibration_x)
        if total < self.minimum_candidates:
            raise InsufficientSampleError(
                f"meta-labeling requires at least {self.minimum_candidates} candidates, got {total}"
            )
        if len(train_x) != len(train_y) or len(calibration_x) != len(calibration_y):
            raise ValueError("feature/label length mismatch")
        self.scaler.fit(train_x)
        scaled_train = [self.scaler.transform_one(row) for row in train_x]
        self.model.fit(scaled_train, train_y)
        probabilities = [self.model.predict_probability(self.scaler.transform_one(row)) for row in calibration_x]
        self.conformal.fit(probabilities, calibration_y)
        self._fitted = True

    def predict(self, features: Sequence[float]) -> ConformalPrediction:
        if not self._fitted:
            raise RuntimeError("meta-label model is not fitted")
        probability = self.model.predict_probability(self.scaler.transform_one(features))
        return self.conformal.predict(probability)
