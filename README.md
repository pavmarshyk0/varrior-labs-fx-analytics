# Varrior Labs FX Analytics

[![CI](https://github.com/pavmarshyk0/varrior-labs-fx-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/pavmarshyk0/varrior-labs-fx-analytics/actions/workflows/ci.yml)

Deterministic EUR/USD quantitative research platform for falsifiable alpha discovery, leakage-safe validation, execution-cost-aware testing, and paper-only experimentation.

> **Research software only.** No profitability claim, no live execution, and no financial advice.

## Status

| Generation | Status | Result |
|---|---|---|
| Gen-1 | `NO_EDGE_FOUND` | Initial momentum / pullback / breakout families failed to establish robust positive OOS expectancy. |
| Gen-2 | `NO_EDGE_FOUND_GEN2` | Diagnostics found no stable pre-entry signal strong enough to justify promotion. |
| Gen-3 | `RESEARCH_IN_PROGRESS` | Event-time price discovery, matched controls and short-horizon microstructure research. |

```text
TRADABLE_EDGE: NOT ESTABLISHED
LIVE_EXECUTION: DISABLED
AI_ALPHA_GENERATION: DISABLED
```

The primary objective is **positive, robust net out-of-sample expectancy after realistic execution costs**.

## Why this project exists

Many trading projects optimize parameters until the historical equity curve looks attractive. This project is intentionally built to make weak ideas fail early and visibly.

Canonical research sequence:

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

A rejected hypothesis is a valid research outcome.

## Architecture

```text
MT5 EUR/USD ticks
        ↓
validation + immutable lineage
        ↓
M5 / M15 / H1 + derived sub-minute research features
        ↓
market state → event → price-discovery state
        ↓
matched controls
        ↓
purged chronological validation + embargo
        ↓
bootstrap confidence intervals + execution-cost stress
        ↓
reproducible research artifacts + read-only dashboard
```

## Implemented infrastructure

- MetaTrader 5 historical tick collection through `copy_ticks_range` only;
- UTC-first tick validation without silently cleaning anomalies;
- resumable Parquet storage with lineage metadata;
- deterministic M5 / M15 / H1 bar construction;
- spread, gap and tick-density diagnostics;
- executable bid/ask research backtesting;
- gross/net R and explicit transaction-cost decomposition;
- volatility-, event- and joint-execution stress scenarios;
- structural invalidation and multiple research exit policies;
- purged chronological walk-forward validation with embargo;
- block-bootstrap confidence intervals and reliability tiers;
- frozen candidate universes and holdout infrastructure;
- deterministic alpha-family benchmarking and Gen-2 failure diagnostics;
- local read-only Streamlit research dashboard;
- automated tests and GitHub CodeQL scanning.

Broker-derived datasets and generated research artifacts are intentionally excluded from the public source tree. See [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).

## What the first experiments found

The first deterministic families did **not** demonstrate robust alpha. Rather than tuning them until a backtest turned green, the project retained the negative evidence and changed the research object itself.

Current canonical conclusions:

```text
GEN-1: NO_EDGE_FOUND
GEN-2: NO_EDGE_FOUND_GEN2
GEN-3: RESEARCH_IN_PROGRESS
```

The public repository therefore represents a **research and validation platform**, not a finished trading strategy.

## Gen-3 Tier A research

### `G3_H01_COHERENT_REPRICING`

Tests whether short-horizon quote-process features add incremental directional information **beyond a matched price impulse**.

Candidate observables include:

- directional bid/ask quote revisions;
- synchronous bid/ask movement;
- tick-arrival intensity and inter-arrival times;
- spread state and spread transition;
- path efficiency;
- short-window realized volatility.

Core research question:

> Does a coherent repricing event outperform an otherwise similar price impulse matched on direction, magnitude, session, volatility and spread context?

### `G3_H02_BREAK_STATE`

Treats a level interaction as one price-discovery process:

```text
BREAK
 ├── ACCEPT  → continuation distribution
 └── REJECT  → reversal distribution
```

PDH/PDL, Asian highs/lows and local extrema are treated as **level generators**, not assumed standalone alpha. A named level must beat matched generic extrema to demonstrate incremental information.

### `G3_H03_MACRO_HAZARD`

A deterministic execution-risk/context layer for scheduled macro events, not a directional alpha source by default.

Primary uses:

- expected volatility hazard;
- spread/slippage regime tagging;
- NO_TRADE research;
- post-event price-discovery context.

## Governance

The project follows several non-negotiable rules:

- no look-ahead information in candidate generation;
- no random train/test split for time-series validation;
- no tuning on a final holdout;
- material hypothesis revisions count as new research trials;
- transaction costs are part of the hypothesis economics;
- statistical significance alone is insufficient: an effect must also clear an economic execution hurdle;
- no martingale, grid, or averaging-down logic;
- no executable `MetaTrader5.order_send` path in the research pipeline.

A universal `RR >= 3` gate is **not** the current research objective. Fixed 3R remains available as a frozen control where useful; structural invalidation and net expectancy drive research decisions.

See [`docs/RESEARCH_GOVERNANCE.md`](docs/RESEARCH_GOVERNANCE.md) for the canonical protocol.

## Installation

Python 3.11+ is required.

Core research package:

```bash
python -m pip install -e .
```

Dashboard dependencies:

```bash
python -m pip install -e ".[dashboard]"
```

MetaTrader 5 integration on Windows:

```bash
python -m pip install -e ".[mt5]"
```

Full local workstation setup on Windows:

```bash
python -m pip install -e ".[dashboard,mt5]"
```

## Tests

```bash
python -m unittest discover -s tests -v
```

GitHub CI runs the suite on Python 3.11 and 3.12.

## Dashboard

The dashboard reads local precomputed research artifacts only:

```bash
python -m streamlit run app.py
```

The public repository intentionally does not contain the broker-derived datasets required to populate the dashboard. Point the sidebar at your local `data/research/alpha/latest` directory after running the research pipeline.

## Useful CLI examples

Validate an exported tick CSV:

```bash
demo-beta validate-ticks ticks.csv
```

Collect historical ticks from a locally logged-in MT5 terminal:

```bash
demo-beta collect-mt5-history \
  --start 2026-07-01T00:00:00Z \
  --end 2026-08-01T00:00:00Z \
  --output-dir data/processed/mt5 \
  --chunk-hours 24 \
  --symbol EURUSD
```

Run the frozen exit-policy research control:

```bash
demo-beta run-exit-ablation \
  --bars-dir data/processed/bars/EURUSD \
  --output-dir data/research/latest \
  --minimum-train-size 20 \
  --validation-size 15 \
  --candidate-stride-bars 12 \
  --max-holding-bars 36
```

These commands produce research artifacts only. They do not place live orders.

## Gen-3 roadmap

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
M6  G3_H01 coherent repricing: discovery → freeze → confirmation → cost test
 ↓
M7  G3_H02 BREAK → ACCEPT/REJECT research
 ↓
M8  Tier-B research only if Tier-A evidence survives
 ↓
M9  Accumulate a new forward locked holdout
 ↓
M10 Paper trading only after confirmed positive net alpha
```

## Repository policy

Before contributing, read:

- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`SECURITY.md`](SECURITY.md)
- [`docs/RESEARCH_GOVERNANCE.md`](docs/RESEARCH_GOVERNANCE.md)
- [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md)
- [`docs/HANDOFF.md`](docs/HANDOFF.md)

## Safety status

- `tick_state_classifier`: **SHADOW / RESEARCH**
- `online_regime_guard`: **SHADOW**
- `hsmm_regime_filter`: **RESEARCH**
- `tick_burst_intensity`: **RESEARCH feature**
- `meta_label_conformal`: **DISABLED_UNTIL_DETERMINISTIC_EDGE**
- live execution: **DISABLED**

## Project philosophy

The goal is not to maximize historical backtest performance. The goal is to find evidence that survives falsification, independent confirmation, and realistic execution costs before capital is involved.
