from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby
from typing import Iterable, Sequence

from ..contracts import BacktestOutcome, BacktestResult, Candidate, Direction, Tick
from ..data.validation import DataQualityViolation, TickFeedValidator
from ..risk import RiskPolicy


@dataclass(frozen=True, slots=True)
class FillAssumption:
    """Deterministic execution stress assumptions.

    Spread is already embedded in bid/ask prices. Slippage values are adverse
    and expressed in pips. `force_no_fill` exists for missed-fill stress tests;
    no unseeded randomness is used in the deterministic core.
    """

    pip_size: float = 0.0001
    entry_slippage_pips: float = 0.0
    exit_slippage_pips: float = 0.0
    latency_ms: int = 0
    commission_r: float = 0.0
    force_no_fill: bool = False

    def __post_init__(self) -> None:
        if self.pip_size <= 0:
            raise ValueError("pip_size must be positive")
        if self.entry_slippage_pips < 0 or self.exit_slippage_pips < 0:
            raise ValueError("slippage assumptions cannot be negative")
        if self.latency_ms < 0:
            raise ValueError("latency_ms cannot be negative")
        if self.commission_r < 0:
            raise ValueError("commission_r cannot be negative")


@dataclass(frozen=True, slots=True)
class _ExitDecision:
    outcome: BacktestOutcome
    tick: Tick
    ambiguous: bool = False


class ExecutableBidAskBacktester:
    def __init__(
        self,
        risk_policy: RiskPolicy | None = None,
        fills: FillAssumption | None = None,
        feed_validator: TickFeedValidator | None = None,
    ) -> None:
        self.risk_policy = risk_policy or RiskPolicy()
        self.fills = fills or FillAssumption()
        self.feed_validator = feed_validator or TickFeedValidator()

    def simulate(self, candidate: Candidate, ticks: Sequence[Tick]) -> BacktestResult:
        self.risk_policy.validate(candidate)
        quality = self.feed_validator.validate(ticks)
        if not quality.valid:
            raise DataQualityViolation(f"tick feed hard failures: {', '.join(quality.hard_failures)}")
        if self.fills.force_no_fill:
            return self._empty_result(candidate, BacktestOutcome.NO_FILL, ("MISSED_FILL_STRESS",))

        usable_from = candidate.entry_available_msc + self.fills.latency_ms
        entry_idx = next((i for i, t in enumerate(ticks) if t.time_msc >= usable_from), None)
        if entry_idx is None:
            return self._empty_result(candidate, BacktestOutcome.NO_FILL, ("NO_TICK_AT_OR_AFTER_ENTRY",))

        entry_tick = ticks[entry_idx]
        entry_exec = self._entry_executable(candidate.direction, entry_tick)
        entry_fill = self._apply_entry_slippage(candidate.direction, entry_exec)
        if candidate.direction is Direction.LONG and entry_fill <= candidate.stop_loss:
            return self._empty_result(candidate, BacktestOutcome.NO_FILL, ("INVALID_LONG_FILL_VS_STOP",))
        if candidate.direction is Direction.SHORT and entry_fill >= candidate.stop_loss:
            return self._empty_result(candidate, BacktestOutcome.NO_FILL, ("INVALID_SHORT_FILL_VS_STOP",))

        exit_decision = self._find_exit(candidate, ticks[entry_idx + 1 :])
        if exit_decision is None:
            return self._empty_result(
                candidate,
                BacktestOutcome.DATA_EXHAUSTED,
                ("NO_EXECUTABLE_TICK_AT_VERTICAL_BARRIER",),
                entry_tick=entry_tick,
                entry_fill=entry_fill,
            )

        exit_tick = exit_decision.tick
        if exit_decision.ambiguous:
            exit_exec = self._worst_same_timestamp_price(candidate, ticks[entry_idx + 1 :], exit_tick.time_msc)
        else:
            exit_exec = self._exit_executable(candidate.direction, exit_tick)
        exit_fill = self._apply_exit_slippage(candidate.direction, exit_exec)

        sign = 1.0 if candidate.direction is Direction.LONG else -1.0
        risk_unit = candidate.planned_risk_price
        gross_price_pnl = sign * (exit_tick.mid - entry_tick.mid)
        executable_price_pnl = sign * (exit_exec - entry_exec)
        net_price_pnl = sign * (exit_fill - entry_fill)

        gross_r = gross_price_pnl / risk_unit
        spread_cost_r = (gross_price_pnl - executable_price_pnl) / risk_unit
        slippage_cost_r = (executable_price_pnl - net_price_pnl) / risk_unit
        net_r = net_price_pnl / risk_unit - self.fills.commission_r
        label = 1 if exit_decision.outcome is BacktestOutcome.TAKE_PROFIT else 0

        notes: list[str] = []
        if exit_decision.ambiguous:
            notes.append("CONFLICTING_BARRIERS_SAME_TIMESTAMP_CONSERVATIVE")

        return BacktestResult(
            candidate_id=candidate.candidate_id,
            outcome=exit_decision.outcome,
            label=label,
            entry_time_msc=entry_tick.time_msc,
            exit_time_msc=exit_tick.time_msc,
            entry_price=entry_fill,
            exit_price=exit_fill,
            gross_r=gross_r,
            spread_cost_r=spread_cost_r,
            slippage_cost_r=slippage_cost_r,
            commission_cost_r=self.fills.commission_r,
            net_r=net_r,
            planned_rr=candidate.planned_rr,
            risk_fraction=candidate.risk_fraction,
            notes=tuple(notes),
        )

    def _find_exit(self, candidate: Candidate, future_ticks: Sequence[Tick]) -> _ExitDecision | None:
        vertical_tick: Tick | None = None
        for time_msc, group_iter in groupby(future_ticks, key=lambda t: t.time_msc):
            group = list(group_iter)
            if time_msc > candidate.vertical_barrier_msc:
                vertical_tick = group[0]
                break
            tp = any(self._hits_tp(candidate, tick) for tick in group)
            sl = any(self._hits_sl(candidate, tick) for tick in group)
            if tp and sl:
                return _ExitDecision(BacktestOutcome.AMBIGUOUS, group[0], ambiguous=True)
            if sl:
                return _ExitDecision(BacktestOutcome.STOP_LOSS, next(t for t in group if self._hits_sl(candidate, t)))
            if tp:
                return _ExitDecision(BacktestOutcome.TAKE_PROFIT, next(t for t in group if self._hits_tp(candidate, t)))
            if time_msc == candidate.vertical_barrier_msc:
                return _ExitDecision(BacktestOutcome.VERTICAL, group[-1])
        if vertical_tick is not None:
            return _ExitDecision(BacktestOutcome.VERTICAL, vertical_tick)
        return None

    @staticmethod
    def _hits_tp(candidate: Candidate, tick: Tick) -> bool:
        if candidate.direction is Direction.LONG:
            return tick.bid >= candidate.take_profit
        return tick.ask <= candidate.take_profit

    @staticmethod
    def _hits_sl(candidate: Candidate, tick: Tick) -> bool:
        if candidate.direction is Direction.LONG:
            return tick.bid <= candidate.stop_loss
        return tick.ask >= candidate.stop_loss

    @staticmethod
    def _entry_executable(direction: Direction, tick: Tick) -> float:
        return tick.ask if direction is Direction.LONG else tick.bid

    @staticmethod
    def _exit_executable(direction: Direction, tick: Tick) -> float:
        return tick.bid if direction is Direction.LONG else tick.ask

    def _apply_entry_slippage(self, direction: Direction, price: float) -> float:
        slip = self.fills.entry_slippage_pips * self.fills.pip_size
        return price + slip if direction is Direction.LONG else price - slip

    def _apply_exit_slippage(self, direction: Direction, price: float) -> float:
        slip = self.fills.exit_slippage_pips * self.fills.pip_size
        return price - slip if direction is Direction.LONG else price + slip

    def _worst_same_timestamp_price(self, candidate: Candidate, ticks: Iterable[Tick], timestamp: int) -> float:
        same = [t for t in ticks if t.time_msc == timestamp]
        if candidate.direction is Direction.LONG:
            return min(t.bid for t in same)
        return max(t.ask for t in same)

    def _empty_result(
        self,
        candidate: Candidate,
        outcome: BacktestOutcome,
        notes: tuple[str, ...],
        entry_tick: Tick | None = None,
        entry_fill: float | None = None,
    ) -> BacktestResult:
        return BacktestResult(
            candidate_id=candidate.candidate_id,
            outcome=outcome,
            label=None,
            entry_time_msc=entry_tick.time_msc if entry_tick else None,
            exit_time_msc=None,
            entry_price=entry_fill,
            exit_price=None,
            gross_r=None,
            spread_cost_r=None,
            slippage_cost_r=None,
            commission_cost_r=self.fills.commission_r,
            net_r=None,
            planned_rr=candidate.planned_rr,
            risk_fraction=candidate.risk_fraction,
            notes=notes,
        )
