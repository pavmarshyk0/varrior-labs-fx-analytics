# Handoff

## Current state — M4

M1-M3 remain intact. M4 adds strict JSON economic-calendar snapshots with
as-of anti-leakage validation, observed-only post-jump inputs, a resumable MT5
historical tick -> validation -> Parquet pipeline, SHA-256 lineage sidecars,
purged-fold-only session baseline fitting, OOS trade statistics, deterministic
moving-block bootstrap 95% CIs, a frozen ablation matrix, and a lineage-aware
Markdown report renderer. No code path calls `order_send`.

All automated tests currently pass: **63/63** with Python 3.12 in the Codex
workspace using `PYTHONPATH=src python -m unittest discover -s tests -v`.

## Deterministic MT5 UTC bars

Build research bars from immutable collected ticks with fixed UTC, half-open
boundaries (a boundary tick belongs to its next bar):

```
demo-beta build-bars --start 2026-07-01T00:00:00Z --end 2026-08-01T00:00:00Z --input-dir data/processed/mt5 --output-dir data/processed/bars --symbol EURUSD --timeframes M5 M15 H1
```

M5 is built directly from raw MT5 ticks. Each populated row contains UTC bar
bounds, independent bid and ask OHLC, tick count, first/last tick time, exact
spread-pip min/median/p95/max (`pip_size=0.0001`), zero-spread metrics and
maximum intertick gap. Empty bars are never written: coverage in the bar-build
report records `empty_expected_trading_intervals` and
`expected_market_closure_intervals` instead. This prevents fabricated weekend
or forward-filled OHLC.

M15 aggregates M5 and H1 aggregates M15. Open/close use the first/last child;
high/low use extrema; tick counts and raw spread samples are concatenated so
higher-timeframe p95 is exact, never an average of lower-timeframe percentiles.
The report validates tick-count reconciliation, OHLC ordering, and parent/child
open-close reconstruction. It and the derived-bar lineage include source input,
optional audit reference, UTC range, configuration, counts, severity, and a
deterministic SHA-256 payload hash.

Quality flags are observational: `HAS_SUSPICIOUS_GAP` marks a non-closure gap
over the configured 60 seconds (the July 24 16:00 M5 bar is identifiable);
`EXTREME_SPREAD` marks >=5 pips; `ZERO_SPREAD_HEAVY` is >=50% zero spread; and
`INCOMPLETE_OR_EMPTY_INTERVAL` marks higher bars with absent child intervals.
None filters ticks or declares a price invalid. Structural reconciliation errors
are `FAIL`; feed characteristics and missing trading intervals are `WARN`.
Cross-boundary gaps are deterministically owned by the bar containing the next
real tick; that bar records `max_intertick_gap_ms`, `suspicious_gap_count`, and
the prior/next timestamped gap observation. This means distinct suspicious gaps
can legitimately share one flagged bar; reports expose both the number of
flagged bars and the total number of suspicious gaps. Expected Friday-to-Monday
closures are never carried as suspicious gaps.

## MT5 monthly raw-tick audit

Before constructing bars or running a backtest, audit a collected range without
changing any source file:

```
demo-beta audit-mt5-history --start 2026-07-01T00:00:00Z --end 2026-08-01T00:00:00Z --input-dir data/processed/mt5 --symbol EURUSD
```

It writes a deterministic `mt5-history-audit/v1` JSON report containing expected
chunk coverage, chunk/lineage checks, orphan artifacts, timestamp/duplicate/gap
statistics, zero-spread counts and ratios by UTC day/hour, spread and
tick-density distributions by UTC day/hour, and a SHA-256 of the report
payload. Each suspicious trading-period gap has a deterministic observation
with previous/next UTC timestamps, duration in milliseconds and seconds, UTC
date/hour, closure-touch flag, and surrounding bid/ask. A gap completely inside
the Saturday/Sunday UTC closure is excluded; a Friday-to-Monday gap spanning an
expected closure is retained separately in `expected_market_closure_gap_observations`
and does not count as suspicious. Extreme spreads retain every
observation plus UTC day/hour counts, percentage of all ticks, and concentration
in the most affected UTC hour. It is read-only: it neither deletes, fills,
interpolates, winsorizes, nor otherwise modifies ticks.

The verified July 2026 raw MT5/Parquet sample has exact time, bid, and ask
equality; Saturday/Sunday closures are lineage-only `EXPECTED_MARKET_CLOSED`
records, not zero-tick Parquet data. Its audit found 7,312,709 ticks, 706 exact
duplicates (0.009654%), 38,085 equal timestamps (0.520806%), and 68.5268%
zero-spread ticks. Zero spread is a documented feed characteristic, not a
corruption finding. Of 399 observations at least 5 pips wide, 397 occurred in
UTC hour 00; the maximum was 36.8 pips.

`FAIL` means a range is unsafe (missing expected trading artifact, lineage row
mismatch, unexpected empty trading chunk, out-of-order timestamp, non-positive
quote, or crossed quote). `WARN` retains potentially legitimate observations
for review (orphan artifacts, any duplicate ticks, suspicious trading-period
gaps, extreme spreads, or unusually low daily density). `PASS` has neither.
The default review thresholds are explicit in the report and CLI: EURUSD pip
size `0.0001`, suspicious gap `60,000 ms`, extreme spread `5 pips`, and low
density below 20% of the observed median trading-day count. They are review
flags only, configurable, and never cause data removal; they are not claims of
corruption. Calendar-day coverage preserves half-open UTC semantics: it counts
the UTC dates touched by `[start, end)` and never counts an end date at exactly
00:00; `[2026-07-01T00:00:00Z, 2026-08-01T00:00:00Z)` is 31 calendar days.

## Frozen semantics

- `RR >= 3.0` is checked before outcome simulation.
- `risk_fraction <= 0.01`; paper default is `0.005`.
- LONG: entry ask + adverse slippage; barriers on bid.
- SHORT: entry bid - adverse slippage; barriers on ask.
- Bid/ask spread is embedded in executable PnL and is not subtracted again.
- Gross R is mid-to-mid reference PnL; spread/slippage/commission bridge gross R to net R.
- Same-millisecond evidence for both barriers returns `AMBIGUOUS`, label 0, with conservative adverse exit.
- Feed validator reports anomalies but never mutates or silently cleans the input.
- MT5 chunks are complete only when validated Parquet and lineage sidecar both exist; invalid chunks stop, never disappear. Empty chunks whose complete half-open UTC interval falls on Saturday/Sunday are explicitly recorded as `EXPECTED_MARKET_CLOSED` lineage-only skips (no Parquet); all other empty chunks remain `EMPTY_FEED` failures.
- Calendar JSON accepts scheduled fields only; revised/actual values are rejected and snapshot `as_of` controls availability.
- Scheduled high-impact events hard-veto but never generate/change direction.
- Tick/Time/Regime modules remain SHADOW/RESEARCH and cannot execute, block, or open trades without promotion criteria.
- Session median/MAD baselines are fitted separately from each purged training fold, never full history or validation rows.
- M4 bootstrap results and ablation arms have no promotion or execution authority.
- Meta-label fitting remains blocked below 800 total train+calibration candidates.

## Next implementation order

1. Obtain MT5 historical EUR/USD bid/ask ticks, exact broker symbol, and UTC date range. Retain every integrity report, outage and rollover period.
2. Obtain immutable, as-of-dated scheduled EUR/USD calendar snapshots in `data/calendar/`.
3. Build the candidate-event generator, then run only the frozen M4 arms over purged walk-forward OOS observations and write the report.
4. Only after sufficient candidate volume, add DSR/PBO/SPA and prospective paper-trading promotion checks.

Do not implement meta-labeling until roughly 800-1,500 primary candidate events exist. Do not add intraday rates/options modules until baseline evidence justifies their data cost.
