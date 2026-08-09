from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class BacktestOutcome(str, Enum):
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    VERTICAL = "VERTICAL"
    AMBIGUOUS = "AMBIGUOUS"
    NO_FILL = "NO_FILL"
    DATA_EXHAUSTED = "DATA_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class Tick:
    time_msc: int
    bid: float
    ask: float
    flags: int = 0

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def timestamp(self) -> datetime:
        return datetime.fromtimestamp(self.time_msc / 1000.0, tz=UTC)


def _require_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    direction: Direction
    entry: float
    stop_loss: float
    take_profit: float
    entry_available_at: datetime
    max_holding: timedelta
    risk_fraction: float = 0.005
    pair: str = "EUR_USD"
    timeframe: str = "M5"
    candidate: bool = True
    level: float | None = None
    atr_m5: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_available_at", _require_utc(self.entry_available_at, "entry_available_at"))
        if self.max_holding <= timedelta(0):
            raise ValueError("max_holding must be positive")
        if not all(x > 0 for x in (self.entry, self.stop_loss, self.take_profit)):
            raise ValueError("entry, stop_loss and take_profit must be positive")

    @property
    def planned_risk_price(self) -> float:
        return abs(self.entry - self.stop_loss)

    @property
    def planned_reward_price(self) -> float:
        return abs(self.take_profit - self.entry)

    @property
    def planned_rr(self) -> float:
        risk = self.planned_risk_price
        return self.planned_reward_price / risk if risk else float("inf")

    @property
    def entry_available_msc(self) -> int:
        return int(self.entry_available_at.timestamp() * 1000)

    @property
    def vertical_barrier_msc(self) -> int:
        return int((self.entry_available_at + self.max_holding).timestamp() * 1000)


@dataclass(frozen=True, slots=True)
class TickQualityReport:
    tick_count: int
    valid: bool
    timestamp_monotonic: bool
    out_of_order_count: int
    equal_timestamp_count: int
    duplicate_tick_count: int
    duplicate_tick_ratio: float
    crossed_quote_count: int
    nonpositive_quote_count: int
    gap_count: int
    missing_tick_ratio: float | None
    spread_median_pips: float | None
    spread_p95_pips: float | None
    hard_failures: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class BacktestResult:
    candidate_id: str
    outcome: BacktestOutcome
    label: int | None
    entry_time_msc: int | None
    exit_time_msc: int | None
    entry_price: float | None
    exit_price: float | None
    gross_r: float | None
    spread_cost_r: float | None
    slippage_cost_r: float | None
    commission_cost_r: float
    net_r: float | None
    planned_rr: float
    risk_fraction: float
    notes: tuple[str, ...] = field(default_factory=tuple)


def jsonable(value: Any) -> Any:
    """Convert dataclass/enums/datetimes recursively to JSON-safe primitives."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {name: jsonable(getattr(value, name)) for name in value.__dataclass_fields__}
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(v) for v in value]
    return value
