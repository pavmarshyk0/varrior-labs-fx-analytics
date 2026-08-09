"""Broker-feed liquidity-event classifier for deterministic candidate filtering.

Thresholds here are research defaults. They are deliberately simple and must
be frozen and validated walk-forward before any promotion beyond SHADOW.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from math import exp
from statistics import median
from typing import Mapping, Sequence

from demo_beta.analytics.contracts import DecisionEffect, ModelStatus, ModuleOutput
from demo_beta.contracts import Candidate, Direction, Tick
from demo_beta.data.validation import DataQualityViolation, TickFeedValidator
from demo_beta.risk import RiskPolicy


def _mad(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    center = median(values)
    return median(abs(v - center) for v in values)


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return min(hi, max(lo, value))


@dataclass(frozen=True, slots=True)
class RobustStat:
    median: float
    mad: float
    sample_size: int

    def zscore(self, value: float) -> float:
        return (value - self.median) / max(1.4826 * self.mad, 1e-9)


class SessionRobustBaseline:
    """Per-session median/MAD baseline fitted only from supplied historical rows."""

    def __init__(self) -> None:
        self._stats: dict[str, dict[str, RobustStat]] = {}

    def fit(self, feature_rows: Sequence[Mapping[str, float]], session_keys: Sequence[str]) -> None:
        if len(feature_rows) != len(session_keys):
            raise ValueError("feature_rows and session_keys must have equal length")
        grouped: dict[str, dict[str, list[float]]] = {}
        for row, key in zip(feature_rows, session_keys):
            bucket = grouped.setdefault(str(key), {})
            for name, value in row.items():
                bucket.setdefault(name, []).append(float(value))
        self._stats = {
            key: {
                name: RobustStat(median(values), _mad(values), len(values))
                for name, values in columns.items()
                if values
            }
            for key, columns in grouped.items()
        }

    def stat(self, session_key: str, feature: str) -> RobustStat | None:
        return self._stats.get(session_key, {}).get(feature)

    def zscore(self, session_key: str, feature: str, value: float) -> float:
        stat = self.stat(session_key, feature)
        return stat.zscore(value) if stat is not None else 0.0

    def sample_size(self, session_key: str) -> int:
        stats = self._stats.get(session_key, {}).values()
        return min((item.sample_size for item in stats), default=0)


@dataclass(frozen=True, slots=True)
class EventWindow:
    pre: tuple[Tick, ...]
    excursion: tuple[Tick, ...]
    post: tuple[Tick, ...]
    event_time_msc: int
    event_mid: float
    level: float
    threshold: float
    excursion_side: int
    candidate_sign: int
    atr: float

    @property
    def all_ticks(self) -> tuple[Tick, ...]:
        return self.pre + self.excursion + self.post


@dataclass(frozen=True, slots=True)
class LevelExcursionDetector:
    pre_window_ms: int = 30_000
    excursion_window_ms: int = 15_000
    post_window_ms: int = 45_000

    def detect(
        self,
        ticks: Sequence[Tick],
        level: float,
        direction: Direction,
        atr: float,
        spread: float | None = None,
    ) -> EventWindow | None:
        if direction not in {Direction.LONG, Direction.SHORT}:
            raise ValueError("tick-state event requires LONG or SHORT candidate direction")
        if level <= 0 or atr <= 0:
            raise ValueError("level and atr must be positive")
        if not ticks:
            return None
        current_spread = spread if spread is not None else median(t.spread for t in ticks)
        threshold = max(0.1 * atr, 1.5 * max(current_spread, 0.0))
        event_idx = next((i for i, tick in enumerate(ticks) if abs(tick.mid - level) >= threshold), None)
        if event_idx is None:
            return None
        event_tick = ticks[event_idx]
        side = 1 if event_tick.mid > level else -1
        candidate_sign = 1 if direction is Direction.LONG else -1
        t0 = event_tick.time_msc
        pre = tuple(t for t in ticks[:event_idx] if t.time_msc >= t0 - self.pre_window_ms)
        excursion = tuple(t for t in ticks[event_idx:] if t0 <= t.time_msc <= t0 + self.excursion_window_ms)
        post = tuple(
            t for t in ticks[event_idx:] if t0 + self.excursion_window_ms < t.time_msc <= t0 + self.post_window_ms
        )
        if not excursion:
            excursion = (event_tick,)
        return EventWindow(
            pre=pre,
            excursion=excursion,
            post=post,
            event_time_msc=t0,
            event_mid=event_tick.mid,
            level=level,
            threshold=threshold,
            excursion_side=side,
            candidate_sign=candidate_sign,
            atr=atr,
        )


class QuotePressureFeatureExtractor:
    pip_size: float = 0.0001

    @staticmethod
    def _signs(ticks: Sequence[Tick]) -> list[int]:
        signs: list[int] = []
        for left, right in zip(ticks, ticks[1:]):
            delta = right.mid - left.mid
            signs.append(1 if delta > 0 else -1 if delta < 0 else 0)
        return signs

    @staticmethod
    def _imbalance(signs: Sequence[int]) -> float:
        active = [sign for sign in signs if sign]
        return sum(active) / len(active) if active else 0.0

    @staticmethod
    def _persistence(signs: Sequence[int], candidate_sign: int) -> float:
        active = [sign for sign in signs if sign]
        return sum(sign == candidate_sign for sign in active) / len(active) if active else 0.5

    @staticmethod
    def _arrival_rate(ticks: Sequence[Tick]) -> float:
        if len(ticks) < 2:
            return 0.0
        seconds = max((ticks[-1].time_msc - ticks[0].time_msc) / 1000.0, 1e-3)
        return (len(ticks) - 1) / seconds

    @staticmethod
    def _quote_asymmetry(ticks: Sequence[Tick]) -> float:
        # MT5 COPY_TICKS flags: bit 1 (2) BID changed, bit 2 (4) ASK changed.
        bid_updates = sum(bool(t.flags & 2) for t in ticks)
        ask_updates = sum(bool(t.flags & 4) for t in ticks)
        total = bid_updates + ask_updates
        return (bid_updates - ask_updates) / total if total else 0.0

    def compute(
        self,
        event: EventWindow,
        baselines: SessionRobustBaseline | None = None,
        session_key: str = "GLOBAL",
    ) -> dict[str, float]:
        post = event.post or event.excursion
        pre = event.pre or event.excursion[:1]
        all_ticks = event.all_ticks
        pre_signs = self._signs(pre)
        post_signs = self._signs(post)
        intensity = self._arrival_rate(post)
        spreads_pips = [tick.spread / self.pip_size for tick in all_ticks]
        spread_peak = max(spreads_pips, default=0.0)
        post_spread = median([tick.spread / self.pip_size for tick in post])
        base_spread = None
        if baselines is not None:
            stat = baselines.stat(session_key, "spread_pips")
            base_spread = stat.median if stat is not None else None
        spread_normalization = _clip((base_spread or max(post_spread, 1e-9)) / max(post_spread, 1e-9))

        signed_distances = [event.excursion_side * (tick.mid - event.level) for tick in event.excursion]
        max_penetration = max(signed_distances, default=0.0)
        final_mid = post[-1].mid if post else event.excursion[-1].mid
        final_penetration = event.excursion_side * (final_mid - event.level)
        rejection = _clip((max_penetration - final_penetration) / max(max_penetration, 1e-12))
        close_location = _clip(final_penetration / max(max_penetration, 1e-12))
        impact_pips = abs(event.excursion[-1].mid - event.excursion[0].mid) / self.pip_size
        impact_per_tick = impact_pips / max(1, len(event.excursion) - 1)

        intensity_z = baselines.zscore(session_key, "tick_intensity", intensity) if baselines else 0.0
        spread_peak_z = baselines.zscore(session_key, "spread_pips", spread_peak) if baselines else 0.0
        return {
            "tick_intensity": intensity,
            "tick_intensity_zscore": intensity_z,
            "signed_tick_imbalance_pre": self._imbalance(pre_signs) * event.candidate_sign,
            "signed_tick_imbalance_post": self._imbalance(post_signs) * event.candidate_sign,
            "imbalance_persistence": self._persistence(post_signs, event.candidate_sign),
            "spread_peak_pips": spread_peak,
            "spread_peak_zscore": spread_peak_z,
            "spread_normalization": spread_normalization,
            "penetration_atr": max_penetration / event.atr,
            "rejection_ratio": rejection,
            "close_location": close_location,
            "price_impact_pips_per_tick": impact_per_tick,
            "quote_asymmetry": self._quote_asymmetry(all_ticks) * event.candidate_sign,
            "excursion_alignment": float(event.excursion_side * event.candidate_sign),
        }


@dataclass(frozen=True, slots=True)
class StateClassification:
    state: str
    state_probabilities: dict[str, float]
    signal: float
    confidence: float
    margin: float


class TickStateClassifier:
    states = ("SWEEP_RETURN", "DIRECTIONAL_BREAKOUT", "SPREAD_SPIKE", "UNRESOLVED")

    @staticmethod
    def _softmax(scores: Mapping[str, float]) -> dict[str, float]:
        top = max(scores.values())
        weights = {name: exp(4.0 * (score - top)) for name, score in scores.items()}
        total = sum(weights.values())
        return {name: weight / total for name, weight in weights.items()}

    def classify(self, features: Mapping[str, float]) -> StateClassification:
        intensity = _clip((features["tick_intensity_zscore"] + 1.0) / 4.0)
        persistence = _clip(features["imbalance_persistence"])
        spread_norm = _clip(features["spread_normalization"])
        close = _clip(features["close_location"])
        rejection = _clip(features["rejection_ratio"])
        quote = _clip((features["quote_asymmetry"] + 1.0) / 2.0)
        alignment = features["excursion_alignment"]
        reversal = _clip(-features["signed_tick_imbalance_pre"] * features["signed_tick_imbalance_post"])
        spread_shock = _clip(max(0.0, features["spread_peak_zscore"]) / 4.0)

        scores = {
            "DIRECTIONAL_BREAKOUT": _clip(
                0.25 * persistence + 0.20 * spread_norm + 0.20 * close + 0.20 * intensity + 0.15 * quote
            ) * _clip((alignment + 1.0) / 2.0),
            "SWEEP_RETURN": _clip(
                0.30 * rejection + 0.20 * spread_norm + 0.20 * reversal + 0.15 * rejection + 0.15 * (1.0 - close)
            ) * _clip((1.0 - alignment) / 2.0),
            "SPREAD_SPIKE": _clip(0.65 * spread_shock + 0.35 * (1.0 - spread_norm)),
            "UNRESOLVED": 0.35,
        }
        probabilities = self._softmax(scores)
        ranking = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
        state, probability = ranking[0]
        margin = probability - ranking[1][1]
        if state in {"DIRECTIONAL_BREAKOUT", "SWEEP_RETURN"}:
            signal = probability
        elif state == "SPREAD_SPIKE":
            signal = -probability
        else:
            signal = 0.0
        confidence = _clip(0.35 + 1.5 * margin)
        return StateClassification(state, probabilities, signal, confidence, margin)


@dataclass(slots=True)
class TickStateModule:
    baselines: SessionRobustBaseline | None = None
    validator: TickFeedValidator = TickFeedValidator()
    detector: LevelExcursionDetector = LevelExcursionDetector()
    extractor: QuotePressureFeatureExtractor = QuotePressureFeatureExtractor()
    classifier: TickStateClassifier = TickStateClassifier()
    version: str = "0.1.0"

    def evaluate(self, candidate: Candidate, ticks: Sequence[Tick], session_key: str = "GLOBAL") -> ModuleOutput:
        RiskPolicy().validate(candidate)
        quality = self.validator.validate(ticks)
        if not quality.valid:
            raise DataQualityViolation(f"tick feed hard failures: {', '.join(quality.hard_failures)}")
        if candidate.level is None or candidate.atr_m5 is None:
            raise ValueError("tick-state module requires candidate.level and candidate.atr_m5")
        event = self.detector.detect(ticks, candidate.level, candidate.direction, candidate.atr_m5)
        if event is None:
            return ModuleOutput(
                module="tick_state_classifier",
                version=self.version,
                candidate_id=candidate.candidate_id,
                direction=candidate.direction,
                signal=0.0,
                confidence=0.0,
                valid=True,
                decision_effect=DecisionEffect.NEUTRAL,
                event="NO_LEVEL_EXCURSION",
                generated_at=candidate.entry_available_at,
                research_reliability={"evidence_grade": "B/C", "model_status": ModelStatus.SHADOW.value},
            )

        features = self.extractor.compute(event, self.baselines, session_key)
        result = self.classifier.classify(features)
        baseline_size = self.baselines.sample_size(session_key) if self.baselines else 0
        baseline_factor = min(1.0, baseline_size / 100.0) if baseline_size else 0.5
        confidence = _clip(result.confidence * baseline_factor)
        effect = DecisionEffect.NEUTRAL
        if result.signal > 0.15:
            effect = DecisionEffect.SUPPORT
        elif result.signal < -0.15:
            effect = DecisionEffect.CONTRADICT
        return ModuleOutput(
            module="tick_state_classifier",
            version=self.version,
            candidate_id=candidate.candidate_id,
            direction=candidate.direction,
            signal=result.signal,
            confidence=confidence,
            valid=True,
            decision_effect=effect,
            event=result.state,
            generated_at=event.excursion[-1].timestamp,
            timeframe="TICK_M5",
            features={**features, "state_probabilities": result.state_probabilities},
            evidence=(result.state,),
            data_quality={
                "missing_tick_ratio": quality.missing_tick_ratio,
                "duplicate_tick_ratio": quality.duplicate_tick_ratio,
                "spread_median_pips": quality.spread_median_pips,
            },
            research_reliability={
                "evidence_grade": "B/C",
                "model_status": ModelStatus.SHADOW.value,
                "baseline_sample_size": baseline_size,
                "parameter_status": "UNVALIDATED_RESEARCH_DEFAULT",
            },
        )
