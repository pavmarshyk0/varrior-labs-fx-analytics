from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from ..contracts import Direction


class DecisionEffect(str, Enum):
    SUPPORT = "SUPPORT"
    CONTRADICT = "CONTRADICT"
    SOFT_VETO = "SOFT_VETO"
    HARD_VETO = "HARD_VETO"
    NEUTRAL = "NEUTRAL"


class ModelStatus(str, Enum):
    RESEARCH = "RESEARCH"
    SHADOW = "SHADOW"
    PAPER_APPROVED = "PAPER_APPROVED"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class ModuleOutput:
    module: str
    version: str
    candidate_id: str
    direction: Direction
    signal: float
    confidence: float
    valid: bool
    decision_effect: DecisionEffect
    event: str
    generated_at: datetime
    pair: str = "EUR_USD"
    timeframe: str = "M5"
    candidate_direction_unchanged: bool = True
    market_regime: str | None = None
    features: dict[str, Any] = field(default_factory=dict)
    evidence: tuple[str, ...] = field(default_factory=tuple)
    contradictions: tuple[str, ...] = field(default_factory=tuple)
    invalidation: dict[str, Any] = field(default_factory=dict)
    execution_feasibility: dict[str, Any] = field(default_factory=dict)
    data_quality: dict[str, Any] = field(default_factory=dict)
    research_reliability: dict[str, Any] = field(default_factory=dict)
    lineage_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not -1.0 <= self.signal <= 1.0:
            raise ValueError("signal must be within [-1, 1]")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if not self.candidate_direction_unchanged:
            raise ValueError("secondary modules cannot change candidate direction")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        object.__setattr__(self, "generated_at", self.generated_at.astimezone(UTC))

