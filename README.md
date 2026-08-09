# Varrior Labs FX Analytics

Deterministic EUR/USD quantitative research platform for falsifiable alpha discovery, leakage-safe validation, execution-cost-aware testing, and paper-only experimentation.

> **Research software only.** No profitability claim, no live execution, and no financial advice.

## Current research status

| Generation | Status | Result |
|---|---|---|
| Gen-1 | `NO_EDGE_FOUND` | Baseline momentum, trend-pullback and volatility-breakout research failed to establish robust positive OOS expectancy. |
| Gen-2 | `NO_EDGE_FOUND_GEN2` | Diagnostics found no stable pre-entry feature strong enough to justify promotion of a new executable family. |
| Gen-3 | `RESEARCH_IN_PROGRESS` | Event-time price discovery, matched controls and short-horizon microstructure research. |

**Live execution:** disabled  
**AI alpha generation:** disabled  
**Research objective:** positive, robust **net OOS expectancy after realistic execution costs**.

## Research philosophy

This project is designed to reject weak ideas before capital is involved.

```text
ECONOMIC MECHANISM
        ↓
OBSERVABLE EVENT
        ↓
PREDECLARED HYPOTHESIS
        ↓
MATCHED CONTROL
        ↓
DISCOVERY → FREEZE
        ↓
INDEPENDENT CONFIRMATION
        ↓
TRANSACTION-COST TEST
        ↓
ONLY THEN: TRADING RULE
```

A failed hypothesis is a valid research result. The goal is not to optimize a backtest until it turns green.

## Architecture

```text
MT5 EUR/USD ticks
        ↓
validation + immutable lineage
        ↓
M5 / M15 / H1 + sub-minute research features
        ↓
market state → event → price-discovery state
        ↓
matched controls
        ↓
purged chronological validation + embargo
        ↓
bootstrap confidence intervals + cost stress
        ↓
research dashboard / reproducible artifacts
```

## Implemented infrastructure

- MetaTrader 5 historical tick collection through `copy_ticks_range` only;
- UTC tick validation without silently cleaning anomalies;
- resumable Parquet partitions with immutable lineage sidecars;
- deterministic M5 / M15 / H1 bar construction;
- spread, gap and tick-density diagnostics;
- executable bid/ask research backtester;
- gross/net R and explicit execution-cost decomposition;
- volatility-, event- and joint-execution stress scenarios;
- structural invalidation and multiple research exit policies;
- purged chronological walk-forward validation with embargo;
- block-bootstrap 95% confidence intervals;
- locked-holdout infrastructure and experiment metadata;
- deterministic alpha-family benchmarking and Gen-2 diagnostics;
- local read-only Streamlit research dashboard;
- automated tests, CI and CodeQL.

Large broker datasets and generated research artifacts are intentionally not part of the public source tree.

## What the first experiments found

The first deterministic families did **not** demonstrate robust alpha. Momentum, trend-pullback and volatility-breakout research produced negative or insufficient OOS evidence. Instead of tuning those families until the backtest looked profitable, they were rejected.

Current canonical conclusions:

```text
GEN-1: NO_EDGE_FOUND
GEN-2: NO_EDGE_FOUND_GEN2
GEN-3: RESEARCH_IN_PROGRESS
TRADABLE_EDGE: NOT ESTABLISHED
LIVE_EXECUTION: DISABLED
```

## Gen-3 research portfolio

Gen-3 is qualitatively different from the failed fixed-clock momentum families.

### `G3_H01_COHERENT_REPRICING`

Tests whether short-horizon quote-process features add incremental directional information **beyond a matched price impulse**.

Candidate observables include directional bid/ask quote revisions, synchronous bid/ask movement, tick arrival intensity, inter-arrival time, spread state, path efficiency and short-window realized volatility.

Core matched-control question:

> Does a coherent repricing event outperform an otherwise similar price impulse matched on direction, magnitude, session, volatility and spread context?

### `G3_H02_BREAK_STATE`

Treats a level interaction as one price-discovery process:

```text
BREAK
 ├── ACCEPT  → continuation distribution
 └── REJECT  → reversal distribution
```

PDH/PDL, Asian highs/lows and local extrema are level generators, not assumed standalone alpha. Named levels must beat matched generic extrema to demonstrate incremental information.

### `G3_H03_MACRO_HAZARD`

A deterministic execution-risk/context layer for scheduled macro events, not a directional alpha source by default.

Primary uses include expected volatility hazard, spread/slippage regime tagging, NO_TRADE research and post-event price-discovery context.

## Governance

- no look-ahead information in candidate generation;
- no random train/test split for time-series validation;
- no tuning on a final holdout;
- material hypothesis revisions count as new research trials;
- transaction costs are part of hypothesis economics;
- statistical significance alone is insufficient: an effect must also clear an economic execution hurdle;
- no martingale, grid or averaging-down logic;
- no executable `MetaTrader5.order_send` path in the research pipeline.

A universal `RR >= 3` gate is no longer the research objective. Fixed 3R remains available as a frozen control where useful; structural invalidation and net expectancy drive research decisions.

## Install and test

Python 3.11+ is required.

```bash
python -m pip install -e .
PYTHONPATH=src python -m unittest discover -s tests -v
```

Windows PowerShell:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
```

## Useful commands

Validate an exported tick CSV:

```bash
demo-beta validate-ticks ticks.csv
```

Collect historical ticks from a locally logged-in MT5 terminal:

```bash
demo-beta collect-mt5-history --start 2026-07-01T00:00:00Z --end 2026-08-01T00:00:00Z --output-dir data/processed/mt5 --chunk-hours 24 --symbol EURUSD
```

Run the frozen exit-policy research baseline:

```bash
demo-beta run-exit-ablation --bars-dir data/processed/bars/EURUSD --output-dir data/research/latest --minimum-train-size 20 --validation-size 15 --candidate-stride-bars 12 --max-holding-bars 36
```

These commands produce research artifacts only. They do not place live orders.

## Gen-3 roadmap

```text
M0  Freeze Gen-3 manifest
 ↓
M1  Audit long-history tick lineage
 ↓
M2  DST/session/event-time engine
 ↓
M3  Sub-minute feature materialization
 ↓
M4  Matched-control engine
 ↓
M5  H03 macro-hazard baseline
 ↓
M6  H01 coherent repricing: discovery → freeze → confirmation → cost test
 ↓
M7  H02 BREAK → ACCEPT/REJECT research
 ↓
M8  Tier-B research only if Tier-A evidence survives
 ↓
M9  New forward locked holdout
 ↓
M10 Paper trading only after confirmed net alpha
```

## Safety status

- `tick_state_classifier`: **SHADOW / RESEARCH**
- `online_regime_guard`: **SHADOW**
- `hsmm_regime_filter`: **RESEARCH**
- `tick_burst_intensity`: **RESEARCH feature**
- `meta_label_conformal`: **DISABLED_UNTIL_SAMPLE**
- live execution: **DISABLED**

See [`docs/HANDOFF.md`](docs/HANDOFF.md) for the continuation point.