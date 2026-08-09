# demo-0.0-beta engineering contract

This repository implements the deterministic EUR/USD research system described in the August 2026 research specification.

Non-negotiable rules:

- Pair: EUR/USD. Primary timeframes: M5, M15, H1.
- Planned reward-to-risk must be at least 3.0.
- Risk per trade must never exceed 1% of equity. Paper-beta defaults to 0.5%.
- No martingale, grids, averaging down, or AI-generated direction.
- LONG execution semantics: enter at ask plus adverse slippage; TP/SL are observed on bid.
- SHORT execution semantics: enter at bid minus adverse slippage; TP/SL are observed on ask.
- Preserve gross and net results separately. Never subtract a constant spread after already simulating bid/ask execution.
- Primary observation unit is a candidate event, not an arbitrary M5 candle.
- UTC is canonical. Session logic must use IANA time zones and be DST-aware.
- Never silently delete feed gaps, equal timestamps, out-of-order ticks, crossed quotes, outages, rollover periods, or DST transitions.
- No random train/test split. Research validation must use walk-forward splits with purge and embargo.
- No full-sample normalization, future-close features, revised-calendar leakage, or smoothed future state.
- An ambiguous barrier hit must never be turned into an optimistic winner.
- Advanced models start in RESEARCH/SHADOW. They cannot hard-veto until prospective evidence supports the change.

Before adding a complex module, prove incremental value against the frozen simpler baseline.

