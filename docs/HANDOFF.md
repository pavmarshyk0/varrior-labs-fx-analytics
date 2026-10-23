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
M0  Freeze Gen-3 manifest / experiment registry
 ↓
M1  Audit extended-history tick lineage
 ↓
M2  Build deterministic DST/session/event-time context
 ↓
M3  Materialize minimal sub-minute feature set
 ↓
M4  Implement matched-control engine
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

## Non-negotiable research principle

Do not maximize backtest performance. Maximize the probability that any surviving effect is real.

```text
mechanism → observable event → preregistration → matched control
→ discovery → freeze → independent confirmation → cost test → trading rule
```

If Gen-3 concludes `NO_DIRECTIONAL_EDGE_FOUND_GEN3`, that is a valid result and the project must record it rather than optimize it away.
