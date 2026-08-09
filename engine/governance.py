"""Versioning and live-micro monitoring interfaces; no broker actions exist here."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from statistics import median
from typing import Sequence


@dataclass(frozen=True, slots=True)
class ExperimentIdentity:
    experiment_id: str
    code_version: str
    config_hash: str
    data_range: str
    data_lineage: tuple[str, ...]
    cost_model_version: str
    exit_policy_version: str
    auditor_version: str | None = None
    prompt_hash: str | None = None

    @staticmethod
    def config_digest(serialized_config: str) -> str:
        return sha256(serialized_config.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExecutionObservation:
    real_slippage_pips: float
    expected_slippage_pips: float
    real_cost_r: float
    estimated_cost_r: float


@dataclass(frozen=True, slots=True)
class ExecutionMonitorConfig:
    minimum_trades: int = 30
    median_slippage_ratio_limit: float = 1.5
    p90_slippage_ratio_limit: float = 2.0
    cost_gap_r_limit: float = 0.10


@dataclass(frozen=True, slots=True)
class ExecutionMonitorResult:
    automatic_execution_pause: bool
    reasons: tuple[str, ...]
    observation_count: int


def rolling_execution_monitor(observations: Sequence[ExecutionObservation], *, config: ExecutionMonitorConfig = ExecutionMonitorConfig()) -> ExecutionMonitorResult:
    """Assess the most recent live-micro observations without auto-retuning.

    A pause is a diagnostic state only: callers must preserve diagnostics,
    recalibrate under a new experiment version, rerun paper/stress research,
    and obtain manual approval before resuming.
    """
    window = observations[-config.minimum_trades:]
    if len(window) < config.minimum_trades:
        return ExecutionMonitorResult(False, ("INSUFFICIENT_LIVE_MICRO_OBSERVATIONS",), len(window))
    expected = sorted(item.expected_slippage_pips for item in window)
    real = sorted(item.real_slippage_pips for item in window)
    p90_index = round((len(window) - 1) * .90)
    reasons: list[str] = []
    if median(real) > config.median_slippage_ratio_limit * median(expected): reasons.append("MEDIAN_SLIPPAGE")
    if real[p90_index] > config.p90_slippage_ratio_limit * expected[p90_index]: reasons.append("P90_SLIPPAGE")
    if median(item.real_cost_r - item.estimated_cost_r for item in window) > config.cost_gap_r_limit: reasons.append("COST_GAP")
    return ExecutionMonitorResult(bool(reasons), tuple(reasons), len(window))
