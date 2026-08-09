from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from .backtesting import ExecutableBidAskBacktester, FillAssumption
from .contracts import Candidate, Direction, Tick, jsonable
from .data import TickFeedValidator, load_ticks_csv
from .data.mt5 import MT5TickCollector
from .data.pipeline import HistoricalTickPipeline
from .data.mt5_audit import MT5AuditConfig, MT5HistoryAuditor
from .data.bars import MT5BarBuilder, BarBuildConfig


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_candidate(path: str | Path) -> Candidate:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return Candidate(
        candidate_id=str(payload["candidate_id"]),
        direction=Direction(payload["direction"]),
        entry=float(payload["entry"]),
        stop_loss=float(payload["stop_loss"]),
        take_profit=float(payload["take_profit"]),
        entry_available_at=_parse_utc(payload["entry_available_at"]),
        max_holding=timedelta(minutes=float(payload.get("max_holding_minutes", 90))),
        risk_fraction=float(payload.get("risk_fraction", 0.005)),
        pair=str(payload.get("pair", "EUR_USD")),
        timeframe=str(payload.get("timeframe", "M5")),
        level=float(payload["level"]) if payload.get("level") is not None else None,
        atr_m5=float(payload["atr_m5"]) if payload.get("atr_m5") is not None else None,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="demo-beta")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-ticks", help="audit a tick CSV without cleaning it")
    validate.add_argument("ticks")
    validate.add_argument("--gap-threshold-ms", type=int)
    validate.add_argument("--expected-interval-ms", type=int)

    backtest = sub.add_parser("backtest", help="simulate one deterministic candidate")
    backtest.add_argument("--candidate", required=True)
    backtest.add_argument("--ticks", required=True)
    backtest.add_argument("--entry-slippage-pips", type=float, default=0.0)
    backtest.add_argument("--exit-slippage-pips", type=float, default=0.0)
    backtest.add_argument("--latency-ms", type=int, default=0)
    backtest.add_argument("--commission-r", type=float, default=0.0)
    backtest.add_argument("--force-no-fill", action="store_true")
    collect = sub.add_parser("collect-mt5-history", help="resumable MT5 -> validate -> Parquet collection")
    collect.add_argument("--start", required=True, help="UTC ISO-8601")
    collect.add_argument("--end", required=True, help="UTC ISO-8601")
    collect.add_argument("--output-dir", required=True)
    collect.add_argument("--chunk-hours", type=float, default=24.0)
    collect.add_argument("--symbol", default="EURUSD")
    collect.add_argument("--calendar-snapshot-id")
    collect.add_argument("--record-unavailable-history", action="store_true", help="record empty non-weekend broker responses as NO_BROKER_HISTORY")
    audit = sub.add_parser("audit-mt5-history", help="read-only monthly quality audit of collected MT5 Parquet")
    audit.add_argument("--start", required=True, help="UTC ISO-8601")
    audit.add_argument("--end", required=True, help="UTC ISO-8601")
    audit.add_argument("--input-dir", required=True)
    audit.add_argument("--symbol", default="EURUSD")
    audit.add_argument("--chunk-hours", type=float, default=24.0)
    audit.add_argument("--output")
    audit.add_argument("--pip-size", type=float, default=0.0001)
    audit.add_argument("--suspicious-gap-ms", type=int, default=60_000)
    audit.add_argument("--extreme-spread-pips", type=float, default=5.0)
    audit.add_argument("--low-density-fraction", type=float, default=0.20)
    bars = sub.add_parser("build-bars", help="deterministic MT5 ticks -> M5/M15/H1 UTC bars")
    bars.add_argument("--start", required=True); bars.add_argument("--end", required=True)
    bars.add_argument("--input-dir", required=True); bars.add_argument("--output-dir", required=True)
    bars.add_argument("--symbol", default="EURUSD"); bars.add_argument("--timeframes", nargs="+", default=["M5", "M15", "H1"])
    bars.add_argument("--chunk-hours", type=float, default=24.0); bars.add_argument("--pip-size", type=float, default=.0001)
    bars.add_argument("--suspicious-gap-ms", type=int, default=60_000); bars.add_argument("--extreme-spread-pips", type=float, default=5.0)
    bars.add_argument("--zero-spread-heavy-ratio", type=float, default=.50)
    bars.add_argument("--source-audit-report")
    ablation = sub.add_parser("run-exit-ablation", help="research-only frozen EUR/USD exit-policy OOS ablation")
    ablation.add_argument("--bars-dir", required=True, help="directory containing M5/M15/H1 Parquet folders")
    ablation.add_argument("--output-dir", required=True)
    ablation.add_argument("--symbol", default="EURUSD")
    ablation.add_argument("--start", help="optional UTC ISO-8601")
    ablation.add_argument("--end", help="optional UTC ISO-8601")
    ablation.add_argument("--minimum-train-size", type=int, default=40)
    ablation.add_argument("--validation-size", type=int, default=30)
    ablation.add_argument("--candidate-stride-bars", type=int, default=12)
    ablation.add_argument("--max-holding-bars", type=int, default=36)
    ablation.add_argument("--no-final-holdout", action="store_true")
    alpha = sub.add_parser("run-alpha-benchmark", help="research-only fixed-3R alpha-family benchmark")
    alpha.add_argument("--bars-dir", required=True); alpha.add_argument("--output-dir", required=True); alpha.add_argument("--symbol", default="EURUSD")
    alpha.add_argument("--minimum-train-size", type=int, default=40); alpha.add_argument("--validation-size", type=int, default=30); alpha.add_argument("--candidate-stride-bars", type=int, default=12); alpha.add_argument("--max-holding-bars", type=int, default=36)
    diagnose = sub.add_parser("run-gen2-diagnostics", help="read-only V1 root-cause and outcome-geometry diagnostics")
    diagnose.add_argument("--bars-dir", required=True); diagnose.add_argument("--alpha-dir", required=True); diagnose.add_argument("--output-dir", required=True)
    events = sub.add_parser("run-event-studies", help="research-only discovery/confirmation session-open studies")
    events.add_argument("--bars-dir", required=True); events.add_argument("--output-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "collect-mt5-history":
        pipeline = HistoricalTickPipeline(MT5TickCollector.from_terminal(args.symbol), args.output_dir,
                                          calendar_snapshot_id=args.calendar_snapshot_id,
                                          record_unavailable_history=args.record_unavailable_history)
        chunks = pipeline.collect(_parse_utc(args.start), _parse_utc(args.end),
                                  chunk=timedelta(hours=args.chunk_hours))
        print(json.dumps(jsonable(chunks), indent=2, sort_keys=True))
        return 0
    if args.command == "audit-mt5-history":
        config = MT5AuditConfig(pip_size=args.pip_size, suspicious_gap_ms=args.suspicious_gap_ms,
                                extreme_spread_pips=args.extreme_spread_pips,
                                low_density_fraction_of_median=args.low_density_fraction)
        auditor = MT5HistoryAuditor(args.input_dir, symbol=args.symbol, config=config)
        report = auditor.audit(_parse_utc(args.start), _parse_utc(args.end), chunk=timedelta(hours=args.chunk_hours))
        path = auditor.write_report(report, args.output)
        print(f"{report['severity']}: {report['period_summary']['total_ticks']} ticks; "
              f"coverage {report['coverage']['percentage']:.2f}%; report: {path}")
        return 2 if report["severity"] == "FAIL" else 0
    if args.command == "build-bars":
        start, end, chunk = _parse_utc(args.start), _parse_utc(args.end), timedelta(hours=args.chunk_hours)
        ticks = _load_mt5_parquet_ticks(Path(args.input_dir), args.symbol, start, end, chunk)
        builder = MT5BarBuilder(symbol=args.symbol, config=BarBuildConfig(pip_size=args.pip_size, suspicious_gap_ms=args.suspicious_gap_ms,
            extreme_spread_pips=args.extreme_spread_pips, zero_spread_heavy_ratio=args.zero_spread_heavy_ratio))
        built, report = builder.build(ticks, start, end, tuple(args.timeframes), source_dataset=str(Path(args.input_dir)), source_audit_report=args.source_audit_report)
        paths = builder.write(built, report, args.output_dir)
        print(f"{report['severity']}: {report['input_ticks']} ticks -> " + ", ".join(f"{tf}={count}" for tf, count in report['bar_counts'].items()) + f"; report: {paths['report']}")
        return 2 if report["severity"] == "FAIL" else 0
    if args.command == "run-exit-ablation":
        from engine.exit_ablation_runner import BarDataset, RunnerConfig, run_exit_ablation, write_experiment
        dataset = BarDataset.load(args.bars_dir, symbol=args.symbol,
                                  start=_parse_utc(args.start) if args.start else None,
                                  end=_parse_utc(args.end) if args.end else None)
        config = RunnerConfig(minimum_train_size=args.minimum_train_size, validation_size=args.validation_size,
                              candidate_stride_bars=args.candidate_stride_bars, max_holding_bars=args.max_holding_bars)
        summary, results = run_exit_ablation(dataset, config=config, final_holdout=not args.no_final_holdout)
        output = write_experiment(args.output_dir, summary, results)
        print(f"{summary['status']}: {summary['candidate_count']} frozen candidates; "
              f"{summary['walk_forward']['fold_count']} OOS folds; results: {output}")
        return 0
    if args.command == "run-alpha-benchmark":
        from engine.alpha_families import standard_alpha_families
        from engine.exit_ablation_runner import BarDataset, RunnerConfig, run_exit_ablation, write_experiment
        from engine.trade_research import ExitPolicy
        root = Path(args.output_dir); dataset = BarDataset.load(args.bars_dir, symbol=args.symbol)
        config = RunnerConfig(minimum_train_size=args.minimum_train_size, validation_size=args.validation_size, candidate_stride_bars=args.candidate_stride_bars, max_holding_bars=args.max_holding_bars)
        summaries = {}
        for family in standard_alpha_families(config):
            summary, rows = run_exit_ablation(dataset, config=config, frozen_candidates=family.generate_candidates(dataset), policies=(ExitPolicy.FIXED_RR,))
            write_experiment(root / family.family_id, summary, rows); summaries[family.family_id] = summary
        root.mkdir(parents=True, exist_ok=True); (root / 'families.json').write_text(json.dumps(summaries, indent=2, default=str, sort_keys=True), encoding='utf-8')
        print(f"RESEARCH: {len(summaries)} alpha families; results: {root}")
        return 0
    if args.command == "run-gen2-diagnostics":
        from engine.gen2_diagnostics import run_gen2_diagnostics
        path = run_gen2_diagnostics(args.bars_dir, args.alpha_dir, args.output_dir)
        print(f"RESEARCH: diagnostics written to {path}")
        return 0
    if args.command == "run-event-studies":
        from engine.event_studies import run_session_open_studies
        path=run_session_open_studies(args.bars_dir,args.output_dir); print(f"RESEARCH: event studies written to {path}"); return 0
    ticks = load_ticks_csv(args.ticks)
    if args.command == "validate-ticks":
        report = TickFeedValidator(
            gap_threshold_ms=args.gap_threshold_ms,
            expected_interval_ms=args.expected_interval_ms,
        ).validate(ticks)
        print(json.dumps(jsonable(report), indent=2, sort_keys=True))
        return 0 if report.valid else 2

    candidate = _load_candidate(args.candidate)
    fills = FillAssumption(
        entry_slippage_pips=args.entry_slippage_pips,
        exit_slippage_pips=args.exit_slippage_pips,
        latency_ms=args.latency_ms,
        commission_r=args.commission_r,
        force_no_fill=args.force_no_fill,
    )
    result = ExecutableBidAskBacktester(fills=fills).simulate(candidate, ticks)
    print(json.dumps(jsonable(result), indent=2, sort_keys=True))
    return 0


def _load_mt5_parquet_ticks(input_dir: Path, symbol: str, start: datetime, end: datetime, chunk: timedelta):
    """Read only canonical collected tick Parquet chunks in deterministic order."""
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("build-bars requires pyarrow") from exc
    ticks = []
    current = start
    while current < end:
        chunk_end = min(current + chunk, end)
        name = f"{symbol}_{current:%Y%m%dT%H%M%SZ}_{chunk_end:%Y%m%dT%H%M%SZ}"
        parquet = input_dir / f"{name}.parquet"
        if parquet.exists():
            table = pq.read_table(parquet, columns=["time_msc", "bid", "ask", "flags"])
            ticks.extend(Tick(int(t), float(b), float(a), int(f)) for t, b, a, f in zip(*(table.column(c).to_pylist() for c in ("time_msc", "bid", "ask", "flags"))))
        current = chunk_end
    return ticks


if __name__ == "__main__":
    raise SystemExit(main())
