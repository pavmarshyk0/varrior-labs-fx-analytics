# Varrior Labs FX Analytics — engineering contract

This repository implements a deterministic EUR/USD alpha-research and validation platform. It is research/paper-only software, not a live trading system.

## Canonical state

```text
GEN-1: NO_EDGE_FOUND
GEN-2: NO_EDGE_FOUND_GEN2
GEN-3: RESEARCH_IN_PROGRESS
TRADABLE_EDGE: NOT ESTABLISHED
LIVE_EXECUTION: DISABLED
AI_ALPHA_GENERATION: DISABLED
```

## Non-negotiable engineering rules

- Pair: EUR/USD.
- M5/M15/H1 are context/structure timeframes; Gen-3 may derive sub-minute representations from ticks for event-time research.
- Risk per trade must never exceed 1% of equity. Lower paper/research risk is preferred.
- No martingale, grids, averaging losers, or stop widening to avoid realizing a loss.
- No AI-generated trade direction and no live `MetaTrader5.order_send` path.
- Structural invalidation is preferred to a universal reward/risk target.
- Fixed 3R may be retained as a frozen control, but `RR >= 3` is **not** a universal research or promotion gate.
- LONG execution semantics: enter at ask plus adverse slippage; TP/SL are observed on bid.
- SHORT execution semantics: enter at bid minus adverse slippage; TP/SL are observed on ask.
- Preserve gross and net results separately. Never subtract a constant spread after already simulating bid/ask execution.
- Model correlated execution deterioration through joint stress where applicable.
- Primary observation unit is a preregistered event/candidate, not an arbitrary candle chosen after outcome inspection.
- UTC is canonical. Session logic must use IANA time zones and be DST-aware.
- Never silently delete feed gaps, equal timestamps, out-of-order ticks, crossed quotes, outages, rollover periods, or DST transitions.
- No random train/test split. Use chronological discovery/confirmation with purge and embargo where applicable.
- A dataset inspected during hypothesis design cannot later be called a pristine final holdout for that hypothesis generation.
- No full-sample normalization, future-close features, revised-calendar leakage, or smoothed future state.
- An ambiguous barrier hit must never be turned into an optimistic winner.
- Advanced models start in `RESEARCH`/`SHADOW`; they cannot hard-veto until prospective evidence supports the change.
- Material hypothesis changes after observing results require a new hypothesis/version and count as a new research trial.
- Statistical significance alone is insufficient; effects must clear realistic execution-cost hurdles before promotion.
- Bulk broker-derived data, generated Parquet datasets, credentials and secrets must not be committed.

## Gen-3 research object

Prefer this sequence:

```text
MARKET STATE
→ EVENT
→ PRICE-DISCOVERY / MICROSTRUCTURE STATE
→ MATCHED CONTROL
→ FORWARD OUTCOME DISTRIBUTION
→ INDEPENDENT CONFIRMATION
→ EXECUTION-COST HURDLE
→ ONLY THEN: TRADING RULE
```

Do not rescue weak deterministic evidence with LLMs, TradingAgents, XGBoost, neural networks, RL, genetic optimization, or indicator stacking.

## Current Tier-A priorities

1. `G3_H03_MACRO_HAZARD` — risk/context baseline.
2. `G3_H01_COHERENT_REPRICING` — test quote-process information against matched price impulses.
3. `G3_H02_BREAK_STATE` — classify `BREAK → ACCEPT / REJECT` against simpler matched controls.

Before adding a complex module, prove incremental value against a frozen simpler control and define what evidence would kill the hypothesis.

See `docs/RESEARCH_GOVERNANCE.md`, `docs/DATA_POLICY.md`, and `docs/HANDOFF.md` for the canonical continuation point.
