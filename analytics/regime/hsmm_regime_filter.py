"""Research-only duration-constrained regime filter.

This is a deliberately small HSMM-inspired baseline, not a claimed source of
alpha. It cannot veto trades and exists for later ablation against BOCPD.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HSMMState:
    regime: str
    duration_bars: int
    confidence: float
    model_status: str = "RESEARCH"


class HSMMRegimeFilter:
    def __init__(self, minimum_duration_bars: int = 3) -> None:
        if minimum_duration_bars < 1:
            raise ValueError("minimum_duration_bars must be positive")
        self.minimum_duration_bars = minimum_duration_bars
        self._regime = "NORMAL"
        self._duration = 0
        self._pending: str | None = None
        self._pending_count = 0

    def update(self, volatility_z: float, spread_z: float) -> HSMMState:
        stress = max(volatility_z, spread_z)
        proposed = "HIGH_STRESS" if stress >= 2.5 else "LOW_VOL" if volatility_z <= -1.5 else "NORMAL"
        if proposed == self._regime:
            self._duration += 1
            self._pending = None
            self._pending_count = 0
        else:
            if self._pending == proposed:
                self._pending_count += 1
            else:
                self._pending = proposed
                self._pending_count = 1
            if self._pending_count >= self.minimum_duration_bars:
                self._regime = proposed
                self._duration = self._pending_count
                self._pending = None
                self._pending_count = 0
            else:
                self._duration += 1
        confidence = min(1.0, self._duration / max(1.0, 2.0 * self.minimum_duration_bars))
        return HSMMState(self._regime, self._duration, confidence)
