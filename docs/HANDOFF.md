# Project Handoff — Varrior Labs FX Analytics

## Canonical state

`demo-0.0-beta` is currently a **deterministic EUR/USD alpha-research and validation platform**, not a production trading bot.

```text
GEN-1: NO_EDGE_FOUND
GEN-2: NO_EDGE_FOUND_GEN2
GEN-3: RESEARCH_IN_PROGRESS
TRADABLE_EDGE: NOT ESTABLISHED
LIVE_EXECUTION: DISABLED
AI_ALPHA_GENERATION: DISABLED
```

## 20 August 2026 checkpoint and repository sync warning

The latest verified local workstation state is ahead of GitHub `main`:

- M0, M1, M2, M3A and M3A.1 are complete locally;
- M3B causal materializers for H01 V2 and H02 V3 are implemented locally;
- Dashboard V2.1 is implemented and smoke-tested locally;
- latest reported local suite: `111 passed, 2 skipped, 13 subtests passed`;
- H03 remains `BLOCKED_NO_CALENDAR_DATA`;
- events have not been materialized for Gen-3 evaluation;
- matched controls and forward outcomes have not been computed;
- Gen-3 evidence remains `UNKNOWN`;
- M4 matched-control infrastructure is the next permitted engineering task.

This synchronization branch contains the exact M0-M3B and Dashboard V2.1 source tree. Do not claim public reproducibility or a Gen-3 result until the draft pull request is reviewed and CI reproduces the source-only test suite; `main` remains unchanged.

See [`PROJECT_STATUS.md`](PROJECT_STATUS.md) for the detailed local/public split.

The system must remain research/paper-only until a deterministic hypothesis survives matched controls, chronological confirmation and realistic execution costs.

## What is already implemented

The repository contains the research infrastructure developed through the first two alpha generations:

- MT5 EUR/USD historical tick collection via `copy_ticks_range` only;
- resumable validated Parquet storage and immutable lineage sidecars;
- explicit market-closure and broker-history lineage states;
- deterministic UTC M5/M15/H1 construction;
- spread, gap, density and zero-spread telemetry;
- executable bid/ask research backtesting;
- gross/net R decomposition and transaction-cost modelling;
- volatility/event/joint execution stress;
- structural invalidation and research exit policies;
- purged chronological walk-forward validation and embargo;
- block-bootstrap confidence intervals and reliability tiers;
- candidate-universe freezing and locked-holdout infrastructure;
- deterministic alpha-family benchmark and Gen-2 failure diagnostics;
- local read-only Streamlit dashboard;
- CI/tests and a safety constraint that no live `order_send` path exists.

## Empirical conclusions so far

The original deterministic alpha families did not demonstrate robust positive expectancy.

### Gen-1

Tested fixed-clock families included baseline momentum, trend pullback, volatility breakout and a sparse liquidity-sweep reversal family. The adequately sampled families had negative observed gross expectancy, so exit optimization was not treated as a way to manufacture alpha.

Conclusion: `NO_EDGE_FOUND`.

### Gen-2

Failure analysis examined direction/session slices, target-before-stop geometry and pre-entry feature relationships. No stable feature signal justified promotion of another executable deterministic family.

Conclusion: `NO_EDGE_FOUND_GEN2`.

These failures are evidence and must not be erased through threshold tuning.

## Extended-history and event-study checkpoint

The verified local broker history spans `2024-08 → 2026-08` and contains:

- `51,949,422` EUR/USD ticks;
- `519 COMPLETED` daily chunks;
- `208 EXPECTED_MARKET_CLOSED` chunks;
- `3 NO_BROKER_HISTORY` chunks;
- monthly M5/M15/H1 partitions for the research scope.

The chronological event-study roles are frozen as:

```text
before 2025-08-01              → DISCOVERY
2025-08-01 through 2026-02-01  → CONFIRMATION
2026-02-01 through 2026-08-01  → LOCKED_HOLDOUT
```

The original London/New-York open unconditional means changed sign between
discovery and confirmation, so neither was promoted.

`engine/event_studies.py` now predeclares non-executable studies for session
opens, expanded Asian range, DST-aware 17:00 New-York PDH/PDL, volatility
compression, efficient trend impulse, conditional range mean reversion and a
clearly labelled bar-level microstructure proxy. These definitions create no
Gen-3 candidate automatically. Discovery and confirmation remain separate.
The locked segment records event counts only and never reads or computes
future-price outcomes.

## Gen-3 architecture shift

Gen-3 changes the research object from a fixed-clock indicator signal to an event/process model:

```text
MARKET STATE
    ↓
EVENT
    ↓
PRICE-DISCOVERY / MICROSTRUCTURE STATE
    ↓
MATCHED CONTROL
    ↓
FORWARD OUTCOME DISTRIBUTION
    ↓
INDEPENDENT CONFIRMATION
    ↓
EXECUTION-COST HURDLE
    ↓
ONLY THEN: TRADING RULE
```

The first question is whether an observable state contains incremental information. Entry/SL/TP design comes later.

## Gen-3 Tier-A program

### G3_H03_MACRO_HAZARD — risk/context baseline

Build deterministic scheduled-event hazard tagging before directional microstructure tests. Timestamp-only macro information is primarily a risk/execution layer: expected volatility, spread/slippage regime, blackout/NO_TRADE research and post-event context. It must not be presented as directional alpha without surprise information.

### G3_H01_COHERENT_REPRICING — primary directional experiment

Test whether short-horizon quote-process coherence adds information beyond the price impulse itself.

Candidate observables:

- directional bid/ask quote revisions;
- synchronous bid/ask movement;
- quote/tick arrival intensity;
- inter-arrival distributions;
- spread state and transition;
- path efficiency;
- short-window realized volatility.

The mandatory control is a price impulse matched on direction, magnitude, session, volatility and spread context but lacking the candidate coherence state.

Primary kill criterion: if microstructure proxies add no stable incremental information over the matched price-only impulse, kill H01.

### G3_H02_BREAK_STATE — price-discovery classification

Treat break continuation and failed-break reversal as two states of one event:

```text
BREAK
 ├── ACCEPT  → continuation distribution
 └── REJECT  → reversal distribution
```

PDH/PDL, Asian highs/lows, previous-week levels, round numbers and local extrema are candidate `level_type` generators. A named level has no special status unless it beats matched generic extrema.

Primary kill criterion: if ACCEPT/REJECT classification does not add stable information over simple excursion/wick/return controls, kill or redesign H02 as a context feature.

## Data governance

Historical data used while designing Gen-3 cannot automatically be called a pristine Gen-3 final holdout.

Use chronological roles explicitly:

```text
older history              → DISCOVERY
later independent history  → CONFIRMATION
already-inspected history  → SECONDARY / HISTORICAL OOS
post-Gen3-freeze data       → NEW FORWARD LOCKED HOLDOUT
```

Never unlock a final holdout to tune thresholds.

## Research firewall

Every material experiment should be registered before outcome inspection with at least:

- hypothesis ID and version;
- dataset role/fingerprint;
- feature definition hash;
- parameter/config hash;
- matched-control definition;
- outcome horizons;
- cost model version;
- timestamp of freeze.

A material change after observing results is a **new research trial/version** and counts toward the multiple-testing burden.

## Outcome hierarchy

Do not jump from statistical significance to `ALPHA_FOUND`.

Recommended evidence states:

```text
NO_INFORMATION
STATISTICAL_EFFECT
ECONOMIC_EFFECT
GROSS_ALPHA
NET_ALPHA
CONFIRMED_ALPHA
PAPER_ELIGIBLE
```

For H01/H02 discovery, first compare forward distributions and matched controls: forward return, directional probability, MFE/MAE, time-to-MFE/MAE, future realized volatility and spread-adjusted move. Only construct a trading rule if incremental information survives.

## Current risk semantics

- risk per trade must never exceed 1%; lower research/paper risk is preferred;
- no martingale, grid or averaging losers;
- never widen a stop to avoid realizing a loss;
- structural invalidation is preferred to a universal reward/risk target;
- fixed 3R remains a useful frozen control where needed, but `RR >= 3` is **not** a universal Gen-3 research gate;
- evaluate net expectancy after spread, slippage and commission;
- correlated execution deterioration must be covered by joint stress, not only independent additive cost terms.

## AI / ML policy

Do not use TradingAgents, LLM signal generation, XGBoost, neural networks, RL or genetic optimization to rescue negative deterministic expectancy.

AI may later serve as a frozen risk/audit/veto layer after deterministic edge is established. It has no alpha-promotion authority now.

## Gen-3 implementation order

```text
M0  Freeze Gen-3 manifest / experiment registry               [COMPLETE LOCALLY]
 ↓
M1  Audit extended-history tick lineage                       [COMPLETE LOCALLY]
 ↓
M2  Build deterministic DST/session/event-time context        [COMPLETE LOCALLY]
 ↓
M3A/M3A.1 Freeze Tier-A definitions and H02 dimensional fix   [COMPLETE LOCALLY]
 ↓
M3B Implement H01 V2 / H02 V3 causal materializers            [COMPLETE LOCALLY; SOURCE SYNC PENDING]
 ↓
M4  Implement matched-control engine                          [NEXT]
 ↓
M5  Establish G3_H03 macro-hazard baseline
 ↓
M6  Run G3_H01 discovery
      ├─ fail → kill hypothesis
      └─ pass → freeze → independent confirmation → cost test
 ↓
M7  Run G3_H02 BREAK→ACCEPT/REJECT research
 ↓
M8  Test Tier-B ideas only if Tier-A evidence justifies more trials
 ↓
M9  Accumulate a new forward locked holdout after Gen-3 freeze
 ↓
M10 Paper trading only after confirmed positive net OOS alpha
```

## Gen-3 M1 lineage audit

`engine/gen3/lineage.py` provides a local, read-only extended-history audit for
MT5 lineage sidecars and Parquet footers. It validates UTC half-open intervals,
allowed statuses, duplicate/overlapping intervals, missing history, sidecar /
Parquet completion consistency, footer row counts, the canonical tick schema,
declared hash format, and monthly M5/M15/H1 partition presence. Its JSON report
has a deterministic SHA-256 fingerprint over normalized audit content; absolute
paths and report creation time are excluded. It does not scan ticks, mutate
Parquet, or recompute file hashes, so an actual local audit remains an explicit
operator action using absolute local paths.

For compatibility with the existing writer, the audit also recognizes a legacy
completed sidecar with no `status` only when it has both a valid quality block
and its paired Parquet file; this is reported as a warning. Any other missing
or unknown status fails closed.

## Gen-3 M2 temporal context

`engine/gen3/temporal.py` provides deterministic UTC-only civil-time context
using IANA `Europe/London`, `America/New_York`, and `Asia/Tokyo` rules. Frozen
local-time windows are Asia core (09:00–15:00 Tokyo), pre-London range
(00:00–07:00 London), London open (07:00–09:00 London), London morning
(08:00–12:00 London), London fix proxy (15:55–16:05 London), NY afternoon
(12:00–16:00 New York), and FX rollover (16:55–17:10 New York). Windows may
overlap; all are `[start,end)`.

`engine/gen3/calendar.py` is an explicit, fail-closed, timestamp-only calendar
adapter. It admits only schedules known at evaluation time, rejects stale or
malformed calendars, and does not consume actual, consensus, surprise, prices,
or outcomes. The frozen temporal configuration hash is
`36e9d009427c470d01bf191a4405e63f9616d6251eac5934c472db55b210b2e2`.
H03 remains `BLOCKED_NO_CALENDAR_DATA` until an authorized historical calendar
snapshot is supplied. M2 is metadata-only for every dataset role.

## Gen-3 M3A executable V2 preregistration

Tier-A V1 remains immutable and historically non-executable: H01 V1 specified
only a 30-second window and H02 V1 supplied no operational parameters. No
market data were opened to resolve that specification gap. `tier_a_v2.json`
therefore preregisters, but does not run, `G3_H01_COHERENT_REPRICING_V2`
(`62331e8bb808f345c230de5821e43f358c524676d015c78f701239c4d09919f0`)
and `G3_H02_BREAK_STATE_V2`
(`64b3b4ba6bb4d746ddf92d9c182fa0a947318a688dbc1db76874d49113225059`).

H01 V2 is a 30-second `(t0-30s,t0]` quote-flow proxy: midpoint imbalance,
bid/ask synchrony, path efficiency, and a causal trailing 30-minute spread
baseline must meet the frozen 0.60 / 0.50 / 0.55 thresholds. Events are first
false-to-true transitions with a global 60-second refractory. H02 V2 uses a
quantized hierarchical round-number family, a causal 60-minute realized
variation scale, frozen oriented BREAK penetration/buffer rules, and completed
one-minute ACCEPTANCE/REJECTION classification. H01 and H02 are independent;
only within-family refractory deduplication applies. Both are
`PREREGISTERED_NOT_RUN`, are permitted only for DISCOVERY/CONFIRMATION price
data, and contain no outcome definition or result. M3B must implement these
frozen definitions without changing them.

## Gen-3 M3A.1 H02 dimensional correction

Before any run, immutable H02 V2 was found to mix a dimensionless
`V_tau=sqrt(sum(log-return^2))` with raw price `spread_at_break` in `max`.
V2 remains unchanged and is recorded as `SUPERSEDED_PRE_RUN_DIMENSIONAL_DEFECT`.
`G3_H02_BREAK_STATE_V3` replaces only H02 V2: `D=s*(ln(mid)-ln(level))`,
`g=ln(ask/bid)`, and `V_tau=sqrt(sum(60 one-minute log-return^2))` are all
log-space quantities. BREAK uses `max(0.10*V_tau,g)` and its inside buffer
uses `max(0.05*V_tau,0.5*g)`; raw spread remains diagnostic only. V3 hashes:
`5c93f89570b4d0a180e37c5c522030f07789d2c4a51dbe7ec4ed2313c8283684`,
`edd12e3a70fa81f2b4e68475f009c1acb099b0320f89f7e8e49f649536f35f66`.
The active set is H01 V2, H02 V3, H03 V1. No price or outcome data were opened.
Next: `M3B_IMPLEMENT_FROZEN_ACTIVE_SET`.

## Local dashboard data integration

The Streamlit dashboard accepts a project root, external data/research root,
legacy `alpha/latest` directory, or direct `families.json`; explicit sidebar
path has precedence over environment, local ignored configuration, and bounded
candidate resolution. Legacy data are visibly labelled `LEGACY GEN-2 — NOT
GEN-3 RESULTS`; Gen-3 remains `NOT_YET_EVALUATED`. Local machine paths live in
ignored `config/local/dashboard_paths.json`; copy the tracked example to
configure another machine. `data/research/gen3/latest/project_status.json` is
a local-only, atomic governance-status artifact with an analytical hash and no
market data or outcomes. Launch with `Start_Varrior_Dashboard.bat`.

The legacy adapter resolves the concrete `families.json` file (not its parent
directory), validates the legacy family mapping before display, and fails
closed with JSON line/column diagnostics on malformed input. The local status
artifact currently reports active stage `M3B`, next step
`M3B_IMPLEMENT_FROZEN_ACTIVE_SET`, and the latest verified suite result.

## Gen-3 M3B frozen active-set implementation

`engine/gen3/events.py` materializes only the frozen executable set:
`G3_H01_COHERENT_REPRICING_V2` and `G3_H02_BREAK_STATE_V3`. It loads the
validated V3 registry and resolves H01 only through the validated immutable V2
reference after matching frozen hashes. H03 is not materialized.

H01 evaluates causal `(t0-30s,t0]` quotes, enforces the causal trailing
`[t0-30m,t0)` baseline, false-to-true triggering, and its global 60-second
refractory. H02 uses only completed `[start,end)` one-minute midpoint closes,
the V3 log-space thresholds and buffers, per-level/oriented-direction
refractory, and blocks conflicting classifications. The versioned causal-event
artifact contains no outcomes, trades, or forward returns.

No market or calendar data were opened. The full available unittest suite
passed: `111 passed, 2 skipped`; `pytest` is not installed in the active
environment. `python -m compileall dashboard engine\\gen3` passed. The next
implementation step is `M4_IMPLEMENT_MATCHED_CONTROL_ENGINE`; H03 remains
`BLOCKED_NO_CALENDAR_DATA`.

## Dashboard V2.1

The local Streamlit dashboard is a read-only research cockpit. Its thin
`dashboard/app.py` entrypoint consumes only bounded local JSON through
`dashboard/artifacts.py` and presentation models in `dashboard/view_models.py`.
It does not import the analytical engine, open tick/bar/Parquet data, connect
to MT5, materialize events, access the locked holdout, or compute outcomes.

Dashboard V2.1 separates code readiness from evidence: M3B is implemented,
H01/H02 event materialization is `NOT RUN`, outcomes are `NOT COMPUTED`, and
the Gen-3 evidence state is `UNKNOWN`. H03 remains
`BLOCKED_NO_CALENDAR_DATA`. The Event Explorer reads only bounded
`gen3-causal-event/v1` JSON artifacts if supplied and rejects malformed,
ambiguous, unsupported, oversized, or outcome-bearing event data.

The canonical launcher remains `Start_Varrior_Dashboard.bat`, retaining port
8501 with its safe 8502 fallback. The tracked local-path example is unchanged.
The dashboard theme is project-local at `.streamlit/config.toml` and has no
external font/CDN dependency.

Verified 2026-08-17 using
`C:\\Users\\User\\Desktop\\varrior-labs-fx-analytics\\.venv\\Scripts\\python.exe`
with `pytest 9.1.1`:

- `-m pytest tests/test_dashboard_artifacts.py -q` → `5 passed`;
- `-m pytest tests/test_gen3_events.py tests/test_gen3_registry_v2.py tests/test_gen3_registry_v3.py -q` → `10 passed, 6 subtests passed`;
- `-m pytest -q` → `111 passed, 2 skipped, 13 subtests passed`;
- `-m compileall dashboard engine\\gen3` → passed.

The local dashboard smoke server returned HTTP 200 at
`http://127.0.0.1:8503`; Streamlit AppTest rendered the Overview, Data health
table, and Technical details without exceptions. No market, outcome, calendar,
or holdout data were accessed. Next permitted analytical work remains
`M4_IMPLEMENT_MATCHED_CONTROL_ENGINE`; it is outside the Dashboard V2.1 scope.

## Non-negotiable research principle

Do not maximize backtest performance. Maximize the probability that any surviving effect is real.

```text
mechanism → observable event → preregistration → matched control
→ discovery → freeze → independent confirmation → cost test → trading rule
```

If Gen-3 concludes `NO_DIRECTIONAL_EDGE_FOUND_GEN3`, that is a valid result and the project must record it rather than optimize it away.
