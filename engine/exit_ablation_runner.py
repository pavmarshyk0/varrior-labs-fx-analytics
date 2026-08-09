"""Frozen candidate-event, purged walk-forward exit-policy ablation runner.

Research only.  It reads closed EUR/USD bars, never sends an order, and uses a
conservative bar-path evaluator when ticks are not supplied.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from demo_beta.contracts import Direction
from .ablation import exit_policy_ablation_matrix
from .costs_model import CostsModel, ExecutionRegime
from .research_statistics import TradeObservation, block_bootstrap_expectancy_ci, performance_statistics
from .trade_research import (CandidateTarget, ExitPolicy, InvalidationKind, StructuralInvalidation, TargetType,
                             fixed_r_target)
from .walk_forward import EventInterval, lock_final_holdout, purged_walk_forward_splits

INVALID_FLAGS = frozenset({"HAS_SUSPICIOUS_GAP", "EXTREME_SPREAD", "INCOMPLETE_OR_EMPTY_INTERVAL"})

def _utc(value: str | datetime) -> datetime:
    if isinstance(value, str): value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None: raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)

def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()

@dataclass(frozen=True, slots=True)
class CandidateEvent:
    candidate_id: str; timestamp: datetime; pair: str; direction: Direction; setup_type: str
    entry_price: float; structural_invalidation: StructuralInvalidation; source_timeframe: str
    regime: str; session: str; feature_snapshot: Mapping[str, float]; reason_codes: tuple[str, ...]
    valid: bool; data_quality_state: str
    family_id: str = "BASELINE_MOMENTUM_V1"; family_version: str = "v1"
    def __post_init__(self) -> None: object.__setattr__(self, "timestamp", _utc(self.timestamp))

@dataclass(frozen=True, slots=True)
class RunnerConfig:
    max_holding_bars: int = 36; candidate_stride_bars: int = 12; atr_lookback: int = 12
    minimum_train_size: int = 40; validation_size: int = 30; embargo_bars: int = 36
    final_holdout_fraction: float = .20; pip_size: float = .0001; bootstrap_samples: int = 500
    def __post_init__(self) -> None:
        if min(self.max_holding_bars, self.candidate_stride_bars, self.atr_lookback, self.minimum_train_size, self.validation_size) < 1: raise ValueError("positive runner sizes required")

@dataclass(frozen=True, slots=True)
class Evaluation:
    candidate_id: str; fold_id: int; exit_policy: str; cost_scenario: str; outcome: str
    entry_timestamp: datetime; exit_timestamp: datetime | None; gross_r: float | None; net_r: float | None
    cost_drag_r: float | None; mfe_r: float | None; mae_r: float | None; holding_bars: int | None
    regime: str; session: str; setup_type: str

class BarDataset:
    def __init__(self, bars: Mapping[str, list[dict[str, Any]]], manifest: Mapping[str, Any]) -> None:
        self.bars, self.manifest = bars, manifest

    @classmethod
    def load(cls, root: str | Path, *, symbol: str = "EURUSD", start: datetime | None = None, end: datetime | None = None) -> "BarDataset":
        try:
            import pyarrow.parquet as pq
        except ImportError as exc: raise RuntimeError("run-exit-ablation requires pyarrow") from exc
        root = Path(root); rows: dict[str, list[dict[str, Any]]] = {}
        sources: dict[str, str] = {}
        for tf in ("M5", "M15", "H1"):
            files = sorted((root / tf).glob("*.parquet"))
            if not files: raise FileNotFoundError(f"no {tf} Parquet under {root}")
            records: list[dict[str, Any]] = []
            for path in files:
                records.extend(pq.read_table(path).to_pylist()); sources[tf] = str(path)
            records.sort(key=lambda row: row["bar_start"])
            rows[tf] = [r for r in records if r["symbol"] == symbol and (start is None or _utc(r["bar_start"]) >= start) and (end is None or _utc(r["bar_start"]) < end)]
        m5 = rows["M5"]
        if not m5: raise ValueError("no selected M5 rows")
        invalid = sum(bool(set(row.get("quality_flags") or ()) & INVALID_FLAGS) for row in m5)
        manifest = {"symbol": symbol, "start": m5[0]["bar_start"], "end": m5[-1]["bar_end"], "row_counts": {tf: len(value) for tf, value in rows.items()}, "source_files": sources, "invalid_m5_bars": invalid, "quality_policy": "exclude HAS_SUSPICIOUS_GAP, EXTREME_SPREAD, INCOMPLETE_OR_EMPTY_INTERVAL; retain zero-spread observations as flagged", "dataset_fingerprint": _digest({tf: [(r["bar_start"], r["bid_close"], r.get("quality_flags", [])) for r in values] for tf, values in rows.items()})}
        return cls(rows, manifest)

def _session(timestamp: datetime) -> str:
    hour = timestamp.hour
    return "ASIA" if hour < 7 else "LONDON" if hour < 13 else "NY" if hour < 21 else "ROLLOVER"

def _closed_bar(rows: Sequence[dict[str, Any]], timestamp: datetime) -> dict[str, Any] | None:
    candidates = [row for row in rows if _utc(row["bar_end"]) <= timestamp]
    return candidates[-1] if candidates else None

class BaselineCandidateGenerator:
    """Small, predeclared closed-bar momentum generator for exit-policy research."""
    def __init__(self, config: RunnerConfig) -> None: self.config = config
    def generate(self, dataset: BarDataset) -> list[CandidateEvent]:
        m5, m15, h1 = dataset.bars["M5"], dataset.bars["M15"], dataset.bars["H1"]; result = []
        for i in range(self.config.atr_lookback, len(m5) - 1, self.config.candidate_stride_bars):
            row = m5[i]; timestamp = _utc(row["bar_end"])
            if set(row.get("quality_flags") or ()) & INVALID_FLAGS: continue
            m15_closed, h1_closed = _closed_bar(m15, timestamp), _closed_bar(h1, timestamp)
            if m15_closed is None or h1_closed is None: continue
            direction = Direction.LONG if row["bid_close"] >= row["bid_open"] else Direction.SHORT
            if (direction is Direction.LONG and m15_closed["bid_close"] < m15_closed["bid_open"]) or (direction is Direction.SHORT and m15_closed["bid_close"] > m15_closed["bid_open"]): continue
            ranges = [m5[j]["bid_high"] - m5[j]["bid_low"] for j in range(i - self.config.atr_lookback, i)]
            buffer = max(median(ranges) * .10, self.config.pip_size)
            entry = m5[i + 1]["ask_open"] if direction is Direction.LONG else m5[i + 1]["bid_open"]
            stop = row["bid_low"] - buffer if direction is Direction.LONG else row["ask_high"] + buffer
            invalidation = StructuralInvalidation(direction, entry, stop, "CLOSED_M5_SWING", "M5", int(timestamp.timestamp() * 1000), InvalidationKind.SWING)
            if not invalidation.valid: continue
            event_id = f"{dataset.manifest['symbol']}-{timestamp:%Y%m%dT%H%M%SZ}-{direction.value}"
            result.append(CandidateEvent(event_id, timestamp, "EUR_USD", direction, "CLOSED_BAR_MOMENTUM", entry, invalidation, "M5", "BULL" if h1_closed["bid_close"] >= h1_closed["bid_open"] else "BEAR", _session(timestamp), {"m5_close_minus_open": row["bid_close"] - row["bid_open"], "m15_close_minus_open": m15_closed["bid_close"] - m15_closed["bid_open"], "atr_proxy": median(ranges)}, ("CLOSED_M5", "CLOSED_M15", "CLOSED_H1"), True, "VALID", "BASELINE_MOMENTUM_V1", "v1"))
        return result

def _targets(event: CandidateEvent) -> dict[ExitPolicy, tuple[CandidateTarget, ...]]:
    risk = event.structural_invalidation.stop_distance; fixed = tuple(fixed_r_target(event.direction, event.entry_price, risk, r, int(event.timestamp.timestamp() * 1000)) for r in (1., 1.5, 2., 3., 4.))
    structure = CandidateTarget(fixed[2].price, fixed[2].gross_r, fixed[2].net_r_estimate, TargetType.STRUCTURAL, "H1_DIRECTIONAL_STRUCTURE", 0, fixed[2].timestamp_msc)
    dynamic = fixed[3] if event.regime == "BULL" and event.direction is Direction.LONG or event.regime == "BEAR" and event.direction is Direction.SHORT else fixed[1]
    return {ExitPolicy.FIXED_RR: (fixed[3],), ExitPolicy.DYNAMIC_RR: (dynamic,), ExitPolicy.STRUCTURE_TARGET: (structure,), ExitPolicy.PARTIAL_TRAILING: (fixed[0], fixed[3])}

def _hit(event: CandidateEvent, row: Mapping[str, Any], price: float, is_stop: bool) -> bool:
    if event.direction is Direction.LONG: return row["bid_low"] <= price if is_stop else row["bid_high"] >= price
    return row["ask_high"] >= price if is_stop else row["ask_low"] <= price

def evaluate_event(event: CandidateEvent, future: Sequence[dict[str, Any]], policy: ExitPolicy, scenario: str, costs: CostsModel, config: RunnerConfig, fold_id: int) -> Evaluation:
    targets = _targets(event)[policy]; risk = event.structural_invalidation.stop_distance; path = list(future[:config.max_holding_bars]); mfe = mae = 0.; partial = False
    for pos, row in enumerate(path, 1):
        favorable = (row["bid_high"] - event.entry_price if event.direction is Direction.LONG else event.entry_price - row["ask_low"]) / risk
        adverse = (row["bid_low"] - event.entry_price if event.direction is Direction.LONG else event.entry_price - row["ask_high"]) / risk
        mfe, mae = max(mfe, favorable), min(mae, adverse)
        sl = _hit(event, row, event.structural_invalidation.invalidation_price, True); hits = [_hit(event, row, target.price, False) for target in targets]
        if sl and any(hits): # no tick/lower-timeframe path: never turn it into a winner
            outcome, gross = "AMBIGUOUS_CONSERVATIVE_STOP", -1.
        elif sl: outcome, gross = "STOP_LOSS", -1.
        elif policy is ExitPolicy.PARTIAL_TRAILING and hits[0] and not partial: partial = True; continue
        elif hits[-1]: outcome, gross = "TAKE_PROFIT", targets[-1].gross_r if not partial else .5 * targets[0].gross_r + .5 * targets[-1].gross_r
        else: continue
        regime = ExecutionRegime.JOINT_EXECUTION_STRESS if scenario == "JOINT_EXECUTION_STRESS" else ExecutionRegime.NORMAL
        multiplier = float(scenario.split("_")[1][:-1]) if scenario.startswith("BASELINE_") else 1.
        estimate = costs.estimate_r(event.session, event.regime, event.direction.value, risk_price=risk, pip_size=config.pip_size, regime=regime, multiplier=multiplier, stopped=gross < 0)
        return Evaluation(event.candidate_id, fold_id, policy.value, scenario, outcome, event.timestamp, _utc(row["bar_end"]), gross, gross-estimate.total_r, estimate.total_r, mfe, mae, pos, event.regime, event.session, event.setup_type)
    row = path[-1] if path else None
    if row is None: return Evaluation(event.candidate_id, fold_id, policy.value, scenario, "NO_PATH", event.timestamp, None, None, None, None, mfe, mae, None, event.regime, event.session, event.setup_type)
    close = row["bid_close"] if event.direction is Direction.LONG else row["ask_close"]
    gross = (close-event.entry_price if event.direction is Direction.LONG else event.entry_price-close) / risk
    estimate = costs.estimate_r(event.session, event.regime, event.direction.value, risk_price=risk, pip_size=config.pip_size)
    return Evaluation(event.candidate_id, fold_id, policy.value, scenario, "VERTICAL", event.timestamp, _utc(row["bar_end"]), gross, gross-estimate.total_r, estimate.total_r, mfe, mae, len(path), event.regime, event.session, event.setup_type)

def run_exit_ablation(dataset: BarDataset, *, config: RunnerConfig = RunnerConfig(), costs: CostsModel | None = None, final_holdout: bool = True,
                      frozen_candidates: Sequence[CandidateEvent] | None = None, policies: Sequence[ExitPolicy] | None = None) -> tuple[dict[str, Any], list[Evaluation]]:
    costs = costs or CostsModel(); candidates = list(frozen_candidates) if frozen_candidates is not None else BaselineCandidateGenerator(config).generate(dataset); fingerprint = _digest([candidate.candidate_id for candidate in candidates]); policies = tuple(policies or tuple(ExitPolicy))
    events = [EventInterval(c.timestamp, c.timestamp + timedelta(minutes=5 * config.max_holding_bars)) for c in candidates]
    holdout = lock_final_holdout(events, holdout_size=max(1, int(len(events) * config.final_holdout_fraction))) if final_holdout and len(events) > 2 else None
    usable = len(candidates) - (len(holdout.indices) if holdout else 0); splits = purged_walk_forward_splits(events[:usable], minimum_train_size=config.minimum_train_size, validation_size=config.validation_size, embargo=timedelta(minutes=5 * config.embargo_bars)) if usable else []
    m5_index = {_utc(row["bar_start"]): index for index, row in enumerate(dataset.bars["M5"])}; result: list[Evaluation] = []
    for fold_id, split in enumerate(splits):
        # The generator/cost configuration is predeclared and frozen; only TEST indices are evaluated.
        for idx in split.validation_indices:
            c = candidates[idx]; start = m5_index.get(c.timestamp)
            if start is None: continue
            path = dataset.bars["M5"][start:]
            for arm in policies:
                for scenario in ("BASELINE_1X", "BASELINE_1.25X", "BASELINE_1.5X", "BASELINE_2X", "JOINT_EXECUTION_STRESS"):
                    result.append(evaluate_event(c, path, arm, scenario, costs, config, fold_id))
    summary: dict[str, Any] = {"schema_version": "exit-ablation/v1", "status": "INSUFFICIENT_DATA" if not splits else "RESEARCH", "dataset": dataset.manifest, "candidate_count": len(candidates), "candidate_universe_fingerprint": fingerprint, "same_candidate_universe": True, "candidate_generator": candidates[0].family_id if candidates else "EMPTY", "family_id": candidates[0].family_id if candidates else "EMPTY", "family_version": candidates[0].family_version if candidates else "EMPTY", "walk_forward": {"fold_count": len(splits), "minimum_train_size": config.minimum_train_size, "validation_size": config.validation_size, "embargo_bars": config.embargo_bars, "parameters_frozen_before_test": True}, "final_holdout_status": "LOCKED" if holdout else "NOT_RESERVED", "final_holdout_count": len(holdout.indices) if holdout else 0, "exit_policy_arms": [arm.value for arm in policies], "cost_scenarios": ["BASELINE_1X", "BASELINE_1.25X", "BASELINE_1.5X", "BASELINE_2X", "JOINT_EXECUTION_STRESS"], "config_fingerprint": _digest(asdict(config))}
    metrics: dict[str, Any] = {}
    for policy in policies:
        for scenario in summary["cost_scenarios"]:
            rows = [r for r in result if r.exit_policy == policy.value and r.cost_scenario == scenario and r.net_r is not None]
            returns = [r.net_r for r in rows]; gross = [r.gross_r for r in rows if r.gross_r is not None]
            stats = performance_statistics([TradeObservation(r.exit_timestamp or r.entry_timestamp, r.net_r or 0., r.mae_r or 0., r.mfe_r or 0.) for r in rows])
            ci = block_bootstrap_expectancy_ci(returns, block_size=min(5, len(returns)), samples=config.bootstrap_samples) if returns else None
            metrics[f"{policy.value}:{scenario}"] = {"trades": len(rows), "net_expectancy_r": stats.expectancy_r, "gross_expectancy_r": sum(gross)/len(gross) if gross else None, "cost_drag_r": (sum(r.cost_drag_r or 0. for r in rows)/len(rows)) if rows else None, "max_drawdown_r": stats.maximum_drawdown_r, "win_rate": stats.win_rate, "longest_losing_streak": stats.longest_losing_streak, "ci_95": asdict(ci) if ci else None, "filled_trade_count": len(rows), "no_fill_count": sum(r.outcome == "NO_PATH" for r in result if r.exit_policy == policy.value and r.cost_scenario == scenario)}
    summary["metrics"] = metrics
    return summary, result

def write_experiment(output_dir: str | Path, summary: Mapping[str, Any], results: Sequence[Evaluation]) -> Path:
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=str, sort_keys=True), encoding="utf-8")
    (output / "report.md").write_text("# Exit-policy OOS ablation\n\nStatus: **%s**\n\n- same_candidate_universe: `%s`\n- final_holdout_status: `%s`\n- candidates: %s\n- folds: %s\n\n## OOS metrics\n\n```json\n%s\n```\n" % (summary["status"], summary["same_candidate_universe"], summary["final_holdout_status"], summary["candidate_count"], summary["walk_forward"]["fold_count"], json.dumps(summary["metrics"], indent=2)), encoding="utf-8")
    try:
        import pyarrow as pa, pyarrow.parquet as pq
        pq.write_table(pa.Table.from_pylist([{**asdict(row), "entry_timestamp": row.entry_timestamp.isoformat(), "exit_timestamp": row.exit_timestamp.isoformat() if row.exit_timestamp else None} for row in results]), output / "detailed_results.parquet")
    except ImportError: pass
    return output
