# Research Governance

This document defines the canonical evidence and experiment-control rules for `demo-0.0-beta` / Varrior Labs FX Analytics.

## Purpose

The objective is not to maximize backtest performance. The objective is to maximize the probability that any surviving EUR/USD effect is real, economically executable, and reproducible.

Canonical sequence:

```text
ECONOMIC MECHANISM
→ OBSERVABLE EVENT
→ PREDECLARED HYPOTHESIS
→ MATCHED CONTROL
→ DISCOVERY
→ FREEZE
→ INDEPENDENT CONFIRMATION
→ COST TEST
→ TRADING RULE
```

## Evidence states

A result must not skip directly from `p < 0.05` to `ALPHA_FOUND`.

```text
NO_INFORMATION
STATISTICAL_EFFECT
ECONOMIC_EFFECT
GROSS_ALPHA
NET_ALPHA
CONFIRMED_ALPHA
PAPER_ELIGIBLE
```

Definitions:

- `NO_INFORMATION`: no stable incremental information over the matched control.
- `STATISTICAL_EFFECT`: a repeatable distributional difference exists, but economic executability is not established.
- `ECONOMIC_EFFECT`: effect size is large enough to justify explicit execution modelling.
- `GROSS_ALPHA`: positive gross expectancy under a preregistered trading interpretation.
- `NET_ALPHA`: positive expectancy after realistic spread/slippage/commission assumptions.
- `CONFIRMED_ALPHA`: net alpha survives independent chronological confirmation and robustness checks.
- `PAPER_ELIGIBLE`: governance requirements for forward paper testing are satisfied.

None of these states implies future profitability.

## Hypothesis registry and trial accounting

Before outcome inspection, a material experiment should record:

- hypothesis ID and version;
- economic mechanism;
- dataset role/fingerprint;
- information set available at event time;
- event and control definitions;
- parameter/config hash;
- outcome horizons;
- cost-model version;
- freeze timestamp;
- falsification criteria.

A material change made after seeing results is a new research trial/version. It must not silently overwrite the original hypothesis. This applies to threshold changes, new filters, new session restrictions, exit redesigns, feature additions, or control redefinitions.

## Chronological data roles

Use time-ordered roles rather than random train/test splits:

```text
older history              → DISCOVERY
later independent history  → CONFIRMATION
already-inspected history  → SECONDARY / HISTORICAL OOS
post-freeze data            → FORWARD LOCKED HOLDOUT
```

A dataset inspected while a hypothesis is being designed cannot later be promoted to pristine final holdout status for that hypothesis generation.

## Matched controls

Every special market narrative must compete with a simpler matched control.

Examples:

- coherent repricing vs price impulse matched on direction, magnitude, session, volatility and spread;
- PDH/PDL vs matched generic local extrema;
- Asian-session extreme vs matched range extreme;
- session boundary vs matched high-activity non-boundary window;
- compression event vs matched low-volatility episode;
- failed break vs generic excursion/wick/return behavior.

The research question is incremental information, not whether a named pattern can be found historically.

## Alpha / filter / context / risk classification

Every mechanism should be classified before promotion:

- `ALPHA`: contains directional information that can support a trading rule.
- `FILTER`: changes whether another alpha should be traded.
- `CONTEXT`: changes the expected distribution but is insufficient to trade independently.
- `RISK`: primarily changes execution, exposure, or tail-risk assumptions.

Volatility predictability is not automatically directional alpha. Session timing is not automatically directional alpha. Timestamp-only macro information is currently treated primarily as `RISK/CONTEXT`.

## Transaction-cost hurdle

Short-horizon effects must be judged against realistic execution friction:

- bid/ask spread;
- commission where applicable;
- entry/exit slippage;
- volatility-dependent slippage;
- event slippage;
- abnormal spread states;
- correlated joint-execution stress.

An effect can be statistically real and still be classified `STATISTICAL_EFFECT / NON_TRADABLE` if it does not clear the executable hurdle.

## Risk policy

- maximum risk per trade: 1%;
- lower research/paper risk is preferred;
- no martingale;
- no grid;
- no averaging losers;
- never widen a stop to avoid realizing a loss;
- structural invalidation is preferred to a universal reward/risk target;
- fixed 3R is retained only as a frozen control where useful;
- no universal `RR >= 3` promotion gate.

## Multiple-testing control

The project should minimize effective trial count before applying statistical corrections. Avoid combinatorial threshold × horizon × session × regime searches without economic justification.

Where appropriate, use:

- false-discovery-rate control;
- White's Reality Check;
- Hansen SPA;
- Deflated Sharpe Ratio;
- PBO / CSCV;
- purged chronological cross-validation;
- embargo;
- block or stationary bootstrap;
- parameter stability and regime robustness checks.

The exact method depends on whether the object is an event study, a ranking rule, or a complete trading strategy.

## Gen-3 Tier A

### `G3_H03_MACRO_HAZARD`

Classification: `RISK / CONTEXT`.

Goal: tag scheduled-event hazard for volatility, spread/slippage and NO_TRADE research. Timestamp-only information does not receive directional-alpha status by default.

### `G3_H01_COHERENT_REPRICING`

Classification: candidate `ALPHA`.

Primary question: do short-horizon quote-process features add stable information beyond a matched price impulse?

Kill criterion: if the microstructure proxies add no stable incremental information over the matched price-only control, reject the hypothesis.

### `G3_H02_BREAK_STATE`

Classification: candidate `ALPHA / CONTEXT`, depending on evidence.

Model one latent process:

```text
BREAK
 ├── ACCEPT  → continuation distribution
 └── REJECT  → reversal distribution
```

Named level types have no privileged status until they beat matched generic extrema.

## AI / ML boundary

LLMs, TradingAgents, XGBoost, neural networks, RL, genetic optimization and similar layers must not be used to rescue negative deterministic expectancy.

AI may later serve as a frozen risk/audit/veto layer after deterministic edge is established. It currently has no alpha-promotion authority.

## Valid failure

A valid Gen-3 result can be:

```text
H01 → KILLED
H02 → KILLED
H03 → VALID RISK LAYER
FINAL → NO_DIRECTIONAL_EDGE_FOUND_GEN3
```

That is research progress. Negative evidence must be recorded rather than optimized away.
