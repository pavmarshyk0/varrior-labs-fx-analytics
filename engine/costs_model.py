"""Execution-cost assumptions without double-counting bid/ask spread."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from demo_beta.backtesting.executable import FillAssumption


@dataclass(frozen=True, slots=True)
class CostBucket:
    entry_slippage_pips: float
    exit_slippage_pips: float
    latency_ms: int
    commission_r: float = 0.0
    no_fill_probability: float = 0.0
    stop_slippage_pips: float = 0.0
    rollover_r: float = 0.0
    abnormal_spread_multiplier: float = 1.0
    event_slippage_pips: float = 0.0

    def __post_init__(self) -> None:
        if min(self.entry_slippage_pips, self.exit_slippage_pips, self.latency_ms, self.commission_r,
               self.stop_slippage_pips, self.rollover_r, self.event_slippage_pips) < 0:
            raise ValueError("cost inputs cannot be negative")
        if not 0.0 <= self.no_fill_probability <= 1.0:
            raise ValueError("no_fill_probability must be within [0, 1]")
        if self.abnormal_spread_multiplier < 1.0:
            raise ValueError("abnormal_spread_multiplier must be >= 1")


class ExecutionRegime(str, Enum):
    NORMAL = "NORMAL"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    NEWS_EVENT = "NEWS_EVENT"
    ROLLOVER = "ROLLOVER"
    JOINT_EXECUTION_STRESS = "JOINT_EXECUTION_STRESS"


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """Costs expressed in R, excluding observed bid/ask spread.

    Spread is an execution price property in the backtester.  It is reported
    separately there and must never be charged again here.
    """
    entry_slippage_r: float
    exit_slippage_r: float
    stop_slippage_r: float
    commission_r: float
    rollover_r: float
    regime: ExecutionRegime
    multiplier: float

    @property
    def total_r(self) -> float:
        return self.entry_slippage_r + self.exit_slippage_r + self.stop_slippage_r + self.commission_r + self.rollover_r


@dataclass(slots=True)
class CostsModel:
    """Lookup of pre-fitted empirical buckets plus a conservative fallback.

    The model never adds a separate constant spread charge: executable bid/ask
    prices in the simulator already contain spread.
    """

    fallback: CostBucket = CostBucket(0.2, 0.3, 100, 0.0, 0.0)
    buckets: dict[tuple[str, str, str], CostBucket] = field(default_factory=dict)

    def register(self, session: str, volatility_regime: str, direction: str, bucket: CostBucket) -> None:
        self.buckets[(session.upper(), volatility_regime.upper(), direction.upper())] = bucket

    def resolve(self, session: str, volatility_regime: str, direction: str) -> CostBucket:
        return self.buckets.get((session.upper(), volatility_regime.upper(), direction.upper()), self.fallback)

    def fill_assumption(
        self,
        session: str,
        volatility_regime: str,
        direction: str,
        *,
        deterministic_no_fill_stress: bool = False,
    ) -> FillAssumption:
        bucket = self.resolve(session, volatility_regime, direction)
        return FillAssumption(
            entry_slippage_pips=bucket.entry_slippage_pips,
            exit_slippage_pips=bucket.exit_slippage_pips,
            latency_ms=bucket.latency_ms,
            commission_r=bucket.commission_r,
            force_no_fill=deterministic_no_fill_stress,
        )

    def estimate_r(
        self, session: str, volatility_regime: str, direction: str, *, risk_price: float,
        pip_size: float = 0.0001, regime: ExecutionRegime = ExecutionRegime.NORMAL,
        multiplier: float = 1.0, stopped: bool = False,
    ) -> CostEstimate:
        """Return a deterministic scenario estimate without assuming independence.

        `JOINT_EXECUTION_STRESS` applies a documented coupled scenario: wider
        slippage, a stop-fill deterioration and an event-liquidity penalty.
        It is not a blanket multiplication of every cost field.
        """
        if risk_price <= 0 or pip_size <= 0 or multiplier <= 0:
            raise ValueError("risk_price, pip_size and multiplier must be positive")
        bucket = self.resolve(session, volatility_regime, direction)
        entry, exit_, stop, commission, rollover = (
            bucket.entry_slippage_pips, bucket.exit_slippage_pips, 0.0,
            bucket.commission_r, bucket.rollover_r,
        )
        if regime is ExecutionRegime.HIGH_VOLATILITY:
            entry *= 1.25; exit_ *= 1.5
        elif regime is ExecutionRegime.NEWS_EVENT:
            entry += bucket.event_slippage_pips; exit_ += bucket.event_slippage_pips
        elif regime is ExecutionRegime.ROLLOVER:
            rollover += bucket.rollover_r
        elif regime is ExecutionRegime.JOINT_EXECUTION_STRESS:
            # Correlated shock: liquidity loss widens both legs, and a stop has
            # an additional gap-fill component.  Commission is contractual.
            entry = entry * 2.0 + bucket.event_slippage_pips
            exit_ = exit_ * 2.5 + bucket.event_slippage_pips
            stop = bucket.stop_slippage_pips * 2.0 if stopped else 0.0
            rollover += bucket.rollover_r
        scale = pip_size / risk_price * multiplier
        return CostEstimate(entry * scale, exit_ * scale, stop * scale, commission * multiplier,
                            rollover * multiplier, regime, multiplier)

    def stress_matrix(
        self, session: str, volatility_regime: str, direction: str, *, risk_price: float,
        pip_size: float = 0.0001, stopped: bool = False,
    ) -> dict[str, CostEstimate]:
        """Required baseline multipliers plus deterministic execution regimes."""
        output = {f"BASELINE_{multiple:g}X": self.estimate_r(session, volatility_regime, direction,
                  risk_price=risk_price, pip_size=pip_size, multiplier=multiple, stopped=stopped)
                  for multiple in (1.0, 1.25, 1.5, 2.0)}
        output.update({regime.value: self.estimate_r(session, volatility_regime, direction, risk_price=risk_price,
                       pip_size=pip_size, regime=regime, stopped=stopped)
                       for regime in ExecutionRegime if regime is not ExecutionRegime.NORMAL})
        output[ExecutionRegime.NORMAL.value] = self.estimate_r(session, volatility_regime, direction,
                                                                risk_price=risk_price, pip_size=pip_size)
        return output
