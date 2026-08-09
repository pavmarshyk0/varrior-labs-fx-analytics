from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from ...contracts import Candidate
from ..contracts import DecisionEffect, ModelStatus, ModuleOutput


LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")
FRANKFURT = ZoneInfo("Europe/Berlin")
WARSAW = ZoneInfo("Europe/Warsaw")


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _is_dst(value: datetime) -> bool:
    offset = value.dst()
    return bool(offset and offset != timedelta(0))


class Impact(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True, slots=True)
class MarketClockState:
    utc: datetime
    london: datetime
    new_york: datetime
    frankfurt: datetime
    warsaw: datetime
    dst_state: str

    @property
    def london_minute(self) -> int:
        return self.london.hour * 60 + self.london.minute

    @property
    def new_york_minute(self) -> int:
        return self.new_york.hour * 60 + self.new_york.minute


class MarketClock:
    def from_utc(self, timestamp: datetime) -> MarketClockState:
        utc = _utc(timestamp, "timestamp")
        london = utc.astimezone(LONDON)
        new_york = utc.astimezone(NEW_YORK)
        eu_dst = _is_dst(london)
        us_dst = _is_dst(new_york)
        if eu_dst == us_dst:
            dst_state = "EU_US_ALIGNED"
        elif us_dst:
            dst_state = "US_DST_EU_STANDARD"
        else:
            dst_state = "EU_DST_US_STANDARD"
        return MarketClockState(
            utc=utc,
            london=london,
            new_york=new_york,
            frankfurt=utc.astimezone(FRANKFURT),
            warsaw=utc.astimezone(WARSAW),
            dst_state=dst_state,
        )


@dataclass(frozen=True, slots=True)
class BenchmarkWindowState:
    london_open: bool
    wmr_fix: bool
    new_york_option_cut: bool
    london_open_distance_minutes: float
    wmr_fix_distance_minutes: float
    option_cut_distance_minutes: float


def _distance_minutes(value: datetime, target: time) -> float:
    target_dt = value.replace(hour=target.hour, minute=target.minute, second=0, microsecond=0)
    return (value - target_dt).total_seconds() / 60.0


@dataclass(frozen=True, slots=True)
class BenchmarkWindowRegistry:
    half_width_minutes: int = 15

    def classify(self, state: MarketClockState) -> BenchmarkWindowState:
        london_open_distance = _distance_minutes(state.london, time(8, 0))
        wmr_fix_distance = _distance_minutes(state.london, time(16, 0))
        option_cut_distance = _distance_minutes(state.new_york, time(10, 0))
        width = float(self.half_width_minutes)
        return BenchmarkWindowState(
            london_open=abs(london_open_distance) <= width,
            wmr_fix=abs(wmr_fix_distance) <= width,
            new_york_option_cut=abs(option_cut_distance) <= width,
            london_open_distance_minutes=london_open_distance,
            wmr_fix_distance_minutes=wmr_fix_distance,
            option_cut_distance_minutes=option_cut_distance,
        )


@dataclass(frozen=True, slots=True)
class MacroEvent:
    event_id: str
    event_code: str
    name: str
    currency: str
    scheduled_at: datetime
    impact: Impact
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "scheduled_at", _utc(self.scheduled_at, "scheduled_at"))
        if self.currency not in {"EUR", "USD"}:
            raise ValueError("demo-0.0-beta macro guard accepts EUR or USD events only")


@dataclass(frozen=True, slots=True)
class CalendarSnapshot:
    snapshot_id: str
    as_of: datetime
    source: str
    events: tuple[MacroEvent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", _utc(self.as_of, "as_of"))


class CalendarLeakageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EconomicCalendarAdapter:
    snapshot: CalendarSnapshot

    def assert_available_at(self, timestamp: datetime) -> None:
        candidate_time = _utc(timestamp, "candidate timestamp")
        if self.snapshot.as_of > candidate_time:
            raise CalendarLeakageError(
                f"calendar snapshot {self.snapshot.snapshot_id} was not available at candidate time"
            )

    def events_between(self, start: datetime, end: datetime) -> list[MacroEvent]:
        start_utc = _utc(start, "start")
        end_utc = _utc(end, "end")
        return [event for event in self.snapshot.events if start_utc <= event.scheduled_at <= end_utc]

    def closest_high_impact_event(self, timestamp: datetime, search_window: timedelta) -> MacroEvent | None:
        timestamp_utc = _utc(timestamp, "timestamp")
        events = self.events_between(timestamp_utc - search_window, timestamp_utc + search_window)
        high = [event for event in events if event.impact is Impact.HIGH]
        if not high:
            return None
        return min(high, key=lambda event: abs((timestamp_utc - event.scheduled_at).total_seconds()))


@dataclass(frozen=True, slots=True)
class ScheduledMacroJumpGuard:
    """Scheduled-event veto only; post-jump stabilisation is a later tick-state step.

    The default 5m/15m window is an explicitly unvalidated research starting
    parameter. It must be walk-forward tested and can be overridden by config.
    """

    pre_veto: timedelta = timedelta(minutes=5)
    post_veto: timedelta = timedelta(minutes=15)
    clock: MarketClock = MarketClock()
    version: str = "0.1.0"

    def evaluate(self, candidate: Candidate, calendar: EconomicCalendarAdapter) -> ModuleOutput:
        timestamp = candidate.entry_available_at
        calendar.assert_available_at(timestamp)
        # Candidate may be at most `pre_veto` before a future release or at
        # most `post_veto` after a past release. Keep the window asymmetric.
        nearby = calendar.events_between(timestamp - self.post_veto, timestamp + self.pre_veto)
        high_impact = [event for event in nearby if event.impact is Impact.HIGH]
        event = min(
            high_impact,
            key=lambda item: abs((timestamp - item.scheduled_at).total_seconds()),
            default=None,
        )
        clock_state = self.clock.from_utc(timestamp)

        if event is None:
            return ModuleOutput(
                module="scheduled_macro_jump_guard",
                version=self.version,
                candidate_id=candidate.candidate_id,
                direction=candidate.direction,
                signal=0.0,
                confidence=1.0,
                valid=True,
                decision_effect=DecisionEffect.NEUTRAL,
                event="NO_SCHEDULED_HIGH_IMPACT_EVENT",
                generated_at=timestamp,
                timeframe="TICK_M5",
                features={"dst_state": clock_state.dst_state},
                research_reliability={
                    "evidence_grade": "A",
                    "model_status": ModelStatus.RESEARCH.value,
                    "parameter_status": "UNVALIDATED_RESEARCH_DEFAULT",
                },
                lineage_ids=(calendar.snapshot.snapshot_id,),
            )

        delta_seconds = (timestamp - event.scheduled_at).total_seconds()
        in_window = -self.pre_veto.total_seconds() <= delta_seconds <= self.post_veto.total_seconds()
        if not in_window:  # defensive invariant; the asymmetric query above should guarantee this.
            raise AssertionError("calendar event escaped configured veto bounds")

        return ModuleOutput(
            module="scheduled_macro_jump_guard",
            version=self.version,
            candidate_id=candidate.candidate_id,
            direction=candidate.direction,
            signal=-1.0,
            confidence=1.0,
            valid=False,
            decision_effect=DecisionEffect.HARD_VETO,
            event=event.event_code,
            generated_at=timestamp,
            timeframe="TICK_M5",
            features={
                "seconds_from_release": delta_seconds,
                "currency": event.currency,
                "event_name": event.name,
                "dst_state": clock_state.dst_state,
                "pre_veto_seconds": self.pre_veto.total_seconds(),
                "post_veto_seconds": self.post_veto.total_seconds(),
            },
            evidence=("SCHEDULED_HIGH_IMPACT_EVENT",),
            research_reliability={
                "evidence_grade": "A",
                "model_status": ModelStatus.RESEARCH.value,
                "policy": "NO_TRADE_DURING_SCHEDULED_WINDOW",
                "parameter_status": "UNVALIDATED_RESEARCH_DEFAULT",
            },
            lineage_ids=(calendar.snapshot.snapshot_id, event.event_id),
        )
