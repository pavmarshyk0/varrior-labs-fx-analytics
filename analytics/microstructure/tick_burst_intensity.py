"""Hawkes-inspired exponentially decayed tick-intensity proxy.

This is intentionally a feature generator, not a standalone trading signal.
The research specification grades its incremental EUR/USD edge as unproven.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from statistics import median
from typing import Sequence

from demo_beta.contracts import Tick


def _mad(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    center = median(values)
    return median(abs(v - center) for v in values)


@dataclass(frozen=True, slots=True)
class BurstParameters:
    mu_up: float = 0.25
    mu_down: float = 0.25
    alpha_up: float = 1.0
    alpha_down: float = 1.0
    beta: float = 2.0

    def __post_init__(self) -> None:
        if min(self.mu_up, self.mu_down, self.alpha_up, self.alpha_down, self.beta) <= 0:
            raise ValueError("burst parameters must be positive")


@dataclass(frozen=True, slots=True)
class BurstReading:
    time_msc: int
    lambda_up: float
    lambda_down: float
    directional_excitation: float
    total_intensity: float
    burst_surprise: float | None


class TickBurstIntensity:
    """Stateful online proxy using only current and past midpoint changes."""

    def __init__(self, parameters: BurstParameters | None = None) -> None:
        self.parameters = parameters or BurstParameters()
        self.lambda_up = self.parameters.mu_up
        self.lambda_down = self.parameters.mu_down
        self._previous: Tick | None = None
        self._history: list[float] = []

    def reset(self) -> None:
        self.lambda_up = self.parameters.mu_up
        self.lambda_down = self.parameters.mu_down
        self._previous = None
        self._history.clear()

    def update(self, tick: Tick) -> BurstReading:
        if self._previous is not None and tick.time_msc < self._previous.time_msc:
            raise ValueError("TickBurstIntensity requires nondecreasing tick timestamps")

        if self._previous is not None:
            dt_seconds = max(0.0, (tick.time_msc - self._previous.time_msc) / 1000.0)
            decay = exp(-self.parameters.beta * dt_seconds)
            self.lambda_up = self.parameters.mu_up + decay * (self.lambda_up - self.parameters.mu_up)
            self.lambda_down = self.parameters.mu_down + decay * (self.lambda_down - self.parameters.mu_down)

            delta = tick.mid - self._previous.mid
            if delta > 0:
                self.lambda_up += self.parameters.alpha_up
            elif delta < 0:
                self.lambda_down += self.parameters.alpha_down

        total = self.lambda_up + self.lambda_down
        directional = (self.lambda_up - self.lambda_down) / max(total, 1e-12)
        surprise: float | None = None
        if len(self._history) >= 20:
            base = median(self._history)
            scale = 1.4826 * _mad(self._history)
            surprise = (total - base) / max(scale, 1e-9)
        self._history.append(total)
        self._previous = tick
        return BurstReading(
            time_msc=tick.time_msc,
            lambda_up=self.lambda_up,
            lambda_down=self.lambda_down,
            directional_excitation=directional,
            total_intensity=total,
            burst_surprise=surprise,
        )

    def transform(self, ticks: Sequence[Tick]) -> list[BurstReading]:
        return [self.update(tick) for tick in ticks]
