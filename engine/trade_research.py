"""Deterministic trade-research primitives; none provide live execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Mapping, Sequence

from demo_beta.contracts import Direction
from .research_statistics import BootstrapCI


class InvalidationKind(str, Enum):
    SWING = "SWING"
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
    STRUCTURAL_BREAK = "STRUCTURAL_BREAK"
    VOLATILITY_BUFFERED = "VOLATILITY_BUFFERED"


@dataclass(frozen=True, slots=True)
class StructuralInvalidation:
    direction: Direction
    entry: float
    invalidation_price: float
    reason_code: str
    source_timeframe: str
    timestamp_msc: int
    kind: InvalidationKind = InvalidationKind.SWING

    @property
    def stop_distance(self) -> float:
        return abs(self.entry - self.invalidation_price)

    def stop_distance_pips(self, pip_size: float = 0.0001) -> float:
        if pip_size <= 0: raise ValueError("pip_size must be positive")
        return self.stop_distance / pip_size

    @property
    def valid(self) -> bool:
        return self.stop_distance > 0 and ((self.direction is Direction.LONG and self.invalidation_price < self.entry)
                                           or (self.direction is Direction.SHORT and self.invalidation_price > self.entry))


class TargetType(str, Enum):
    FIXED_R = "FIXED_R"
    STRUCTURAL = "STRUCTURAL"
    LIQUIDITY = "LIQUIDITY"
    EXTERNAL = "EXTERNAL"


@dataclass(frozen=True, slots=True)
class CandidateTarget:
    price: float
    gross_r: float
    net_r_estimate: float
    target_type: TargetType
    reason: str
    priority: int
    timestamp_msc: int
    valid: bool = True


def fixed_r_target(direction: Direction, entry: float, stop_distance: float, multiple: float = 3.0,
                   timestamp_msc: int = 0) -> CandidateTarget:
    if stop_distance <= 0 or multiple <= 0: raise ValueError("stop_distance and multiple must be positive")
    price = entry + stop_distance * multiple if direction is Direction.LONG else entry - stop_distance * multiple
    return CandidateTarget(price, multiple, multiple, TargetType.FIXED_R, f"FIXED_{multiple:g}R", 0, timestamp_msc)


class ExitPolicy(str, Enum):
    FIXED_RR = "FIXED_RR"
    DYNAMIC_RR = "DYNAMIC_RR"
    STRUCTURE_TARGET = "STRUCTURE_TARGET"
    PARTIAL_TRAILING = "PARTIAL_TRAILING"


@dataclass(frozen=True, slots=True)
class ExitPlan:
    policy: ExitPolicy
    targets: tuple[CandidateTarget, ...]
    partial_fraction: float = 1.0
    trailing_rule: str | None = None
    break_even_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.targets or not 0 < self.partial_fraction <= 1: raise ValueError("valid targets and partial fraction required")
        if self.break_even_enabled: raise ValueError("break-even requires explicit OOS approval and is off by default")


def choose_exit_plan(policy: ExitPolicy, targets: Sequence[CandidateTarget], *, fixed_r: float = 3.0) -> ExitPlan:
    valid = sorted((target for target in targets if target.valid), key=lambda target: (target.priority, -target.net_r_estimate, target.timestamp_msc))
    if policy is ExitPolicy.FIXED_RR:
        fixed = [target for target in valid if target.target_type is TargetType.FIXED_R and abs(target.gross_r - fixed_r) < 1e-12]
        if not fixed: raise ValueError("fixed-RR plan needs its fixed baseline target")
        return ExitPlan(policy, (fixed[0],))
    if policy is ExitPolicy.STRUCTURE_TARGET:
        structural = [target for target in valid if target.target_type in (TargetType.STRUCTURAL, TargetType.LIQUIDITY)]
        if not structural: raise ValueError("structure policy needs a structural/liquidity target")
        return ExitPlan(policy, (structural[0],))
    if not valid: raise ValueError("exit plan needs at least one valid target")
    if policy is ExitPolicy.PARTIAL_TRAILING and len(valid) >= 2:
        return ExitPlan(policy, (valid[0], valid[1]), partial_fraction=0.5, trailing_rule="STRUCTURAL_TRAIL")
    return ExitPlan(policy, (valid[0],))


class ConfidenceTier(str, Enum):
    INSUFFICIENT = "INSUFFICIENT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    MEDIUM_CONFIDENCE = "MEDIUM_CONFIDENCE"
    NORMAL_RESEARCH_CONFIDENCE = "NORMAL_RESEARCH_CONFIDENCE"


@dataclass(frozen=True, slots=True)
class ReliabilityConfig:
    insufficient_below: int = 30
    low_below: int = 100
    medium_below: int = 200
    shrinkage_prior_weight: float = 50.0

    def tier(self, sample_size: int) -> ConfidenceTier:
        if sample_size < self.insufficient_below: return ConfidenceTier.INSUFFICIENT
        if sample_size < self.low_below: return ConfidenceTier.LOW_CONFIDENCE
        if sample_size < self.medium_below: return ConfidenceTier.MEDIUM_CONFIDENCE
        return ConfidenceTier.NORMAL_RESEARCH_CONFIDENCE


def shrunk_mean(raw_mean: float, sample_size: int, parent_mean: float, *, prior_weight: float = 50.0) -> float:
    if sample_size < 0 or prior_weight < 0: raise ValueError("sample_size and prior_weight cannot be negative")
    return (sample_size * raw_mean + prior_weight * parent_mean) / (sample_size + prior_weight) if sample_size + prior_weight else parent_mean


@dataclass(frozen=True, slots=True)
class ExpectedValue:
    gross_expectancy_r: float
    net_expectancy_r: float
    cost_drag_r: float
    sample_size: int
    confidence_tier: ConfidenceTier
    ci: BootstrapCI | None
    setup: str
    regime: str
    exit_policy: ExitPolicy


def expected_value(*, win_probability: float, gross_win_r: float, gross_loss_r: float, cost_drag_r: float,
                   sample_size: int, reliability: ReliabilityConfig, setup: str, regime: str,
                   exit_policy: ExitPolicy, ci: BootstrapCI | None = None) -> ExpectedValue:
    if not 0 <= win_probability <= 1 or gross_loss_r > 0 or not all(isfinite(v) for v in (gross_win_r, gross_loss_r, cost_drag_r)):
        raise ValueError("invalid expected-value inputs")
    gross = win_probability * gross_win_r + (1 - win_probability) * gross_loss_r
    return ExpectedValue(gross, gross - cost_drag_r, cost_drag_r, sample_size, reliability.tier(sample_size), ci, setup, regime, exit_policy)


class ResearchMode(str, Enum):
    RESEARCH = "RESEARCH"
    STRICT_PAPER = "STRICT_PAPER"


@dataclass(frozen=True, slots=True)
class FeasibilityResult:
    accepted: bool
    reasons: tuple[str, ...]


def feasibility_gates(*, valid_data: bool, invalidation: StructuralInvalidation, risk_fraction: float,
                      ev: ExpectedValue, stress_net_expectancies: Mapping[str, float], mode: ResearchMode,
                      max_drawdown_r: float | None = None, drawdown_ceiling_r: float | None = None) -> FeasibilityResult:
    reasons: list[str] = []
    if not valid_data: reasons.append("INVALID_DATA")
    if not invalidation.valid: reasons.append("INVALID_STRUCTURAL_INVALIDATION")
    if not 0 < risk_fraction <= .01: reasons.append("MAX_RISK_EXCEEDED")
    if ev.confidence_tier is ConfidenceTier.INSUFFICIENT: reasons.append("INSUFFICIENT_SAMPLE")
    if ev.net_expectancy_r <= 0: reasons.append("NON_POSITIVE_NET_EXPECTANCY")
    if stress_net_expectancies.get("BASELINE_1.25X", ev.net_expectancy_r) <= 0: reasons.append("EXECUTION_FRAGILE")
    if drawdown_ceiling_r is not None and max_drawdown_r is not None and max_drawdown_r > drawdown_ceiling_r: reasons.append("DRAWDOWN_CEILING")
    if mode is ResearchMode.STRICT_PAPER and ev.confidence_tier is ConfidenceTier.NORMAL_RESEARCH_CONFIDENCE and (ev.ci is None or ev.ci.lower_95 <= 0): reasons.append("CI_LOWER_NOT_POSITIVE")
    return FeasibilityResult(not reasons, tuple(reasons))


@dataclass(frozen=True, slots=True)
class RankingWeights:
    net_expectancy: float = .35
    stability: float = .20
    confidence: float = .15
    regime_robustness: float = .15
    tail_execution_robustness: float = .15

    def __post_init__(self) -> None:
        if abs(sum((self.net_expectancy, self.stability, self.confidence, self.regime_robustness,
                    self.tail_execution_robustness)) - 1.0) > 1e-9:
            raise ValueError("ranking weights must sum to one")


def weighted_rank_score(metrics: Mapping[str, float], weights: RankingWeights = RankingWeights()) -> float:
    values = (metrics.get("net_expectancy", 0.), metrics.get("stability", 0.), metrics.get("confidence", 0.), metrics.get("regime_robustness", 0.), metrics.get("tail_execution_robustness", 0.))
    if any(not 0 <= value <= 1 for value in values): raise ValueError("ranking inputs must be documented [0,1] normalizations")
    return sum(value * weight for value, weight in zip(values, (weights.net_expectancy, weights.stability,
               weights.confidence, weights.regime_robustness, weights.tail_execution_robustness), strict=True))
