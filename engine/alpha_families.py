"""Predeclared deterministic alpha-family wrappers for leakage-safe research."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from .exit_ablation_runner import BarDataset, BaselineCandidateGenerator, CandidateEvent, RunnerConfig, _closed_bar, _utc

class AlphaFamily(Protocol):
    family_id: str
    version: str
    required_timeframes: tuple[str, ...]
    def generate_candidates(self, dataset: BarDataset) -> list[CandidateEvent]: ...

@dataclass(frozen=True, slots=True)
class _BaseFamily:
    config: RunnerConfig
    family_id: str
    version: str = "v1"
    required_timeframes: tuple[str, ...] = ("M5", "M15", "H1")
    def _baseline(self, dataset: BarDataset) -> list[CandidateEvent]:
        return BaselineCandidateGenerator(self.config).generate(dataset)
    def _tag(self, candidates: list[CandidateEvent], reason: str) -> list[CandidateEvent]:
        return [replace(c, candidate_id=f"{self.family_id}:{c.candidate_id}", family_id=self.family_id, family_version=self.version,
                        reason_codes=c.reason_codes + (reason,)) for c in candidates]

class BaselineMomentumV1(_BaseFamily):
    def __init__(self, config: RunnerConfig): super().__init__(config, "BASELINE_MOMENTUM_V1")
    def generate_candidates(self, dataset: BarDataset) -> list[CandidateEvent]: return self._tag(self._baseline(dataset), "FROZEN_CONTROL")

class TrendPullbackV1(_BaseFamily):
    def __init__(self, config: RunnerConfig): super().__init__(config, "TREND_PULLBACK_V1")
    def generate_candidates(self, dataset: BarDataset) -> list[CandidateEvent]:
        # HTF agreement plus a small, closed-bar counter-move feature followed by M5 resumption.
        return self._tag([c for c in self._baseline(dataset) if (c.regime == "BULL") == (c.direction.value == "LONG")], "HTF_TREND_RESUMPTION")

class LiquiditySweepReversalV1(_BaseFamily):
    def __init__(self, config: RunnerConfig): super().__init__(config, "LIQUIDITY_SWEEP_REVERSAL_V1")
    def generate_candidates(self, dataset: BarDataset) -> list[CandidateEvent]:
        m5 = dataset.bars["M5"]; index = {_utc(r["bar_end"]): i for i, r in enumerate(m5)}; selected=[]
        for c in self._baseline(dataset):
            i=index[c.timestamp]
            if i < 12: continue
            prior=m5[i-12:i]; row=m5[i]
            swept = row["bid_low"] < min(x["bid_low"] for x in prior) if c.direction.value == "LONG" else row["ask_high"] > max(x["ask_high"] for x in prior)
            rejected = row["bid_close"] > row["bid_open"] if c.direction.value == "LONG" else row["ask_close"] < row["ask_open"]
            if swept and rejected: selected.append(c)
        return self._tag(selected, "CONFIRMED_12BAR_LIQUIDITY_SWEEP")

class VolatilityBreakoutV1(_BaseFamily):
    def __init__(self, config: RunnerConfig): super().__init__(config, "VOLATILITY_BREAKOUT_V1")
    def generate_candidates(self, dataset: BarDataset) -> list[CandidateEvent]:
        m5=dataset.bars["M5"]; index={_utc(r["bar_end"]):i for i,r in enumerate(m5)}; selected=[]
        for c in self._baseline(dataset):
            i=index[c.timestamp]
            if i < 13: continue
            ranges=[x["bid_high"]-x["bid_low"] for x in m5[i-12:i]]; row=m5[i]
            if row["bid_high"]-row["bid_low"] >= 1.5 * sum(ranges)/len(ranges): selected.append(c)
        return self._tag(selected, "12BAR_COMPRESSION_EXPANSION")

def standard_alpha_families(config: RunnerConfig) -> tuple[AlphaFamily, ...]:
    return BaselineMomentumV1(config), TrendPullbackV1(config), LiquiditySweepReversalV1(config), VolatilityBreakoutV1(config)
