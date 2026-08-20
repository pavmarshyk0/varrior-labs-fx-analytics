# Project Status — 20 August 2026

This document separates the verified local research checkpoint from the code currently available on GitHub.

## Canonical research state

```text
GEN-1: NO_EDGE_FOUND
GEN-2: NO_EDGE_FOUND_GEN2
GEN-3: RESEARCH_IN_PROGRESS
GEN-3 EVIDENCE: UNKNOWN
TRADABLE_EDGE: NOT ESTABLISHED
LIVE_EXECUTION: DISABLED
AI_ALPHA_GENERATION: DISABLED
```

No Gen-3 profitability, win-rate, expectancy or trading-edge claim is available.

## Milestone status

| Milestone | Status | Meaning |
|---|---|---|
| M0 | Complete locally | Gen-3 manifest and experiment registry frozen. |
| M1 | Complete locally | Extended-history lineage audit completed. |
| M2 | Complete locally | Deterministic UTC/DST/session context completed. |
| M3A | Complete locally | Tier-A hypotheses preregistered; a dimensional defect in H02 V2 was identified before outcome evaluation. |
| M3A.1 | Complete locally | H02 dimensional correction frozen as H02 V3 without rewriting earlier versions. |
| M3B | Implementation complete locally | Causal H01 V2 and H02 V3 event materializers implemented. Real market events have not been materialized for Gen-3 evaluation. |
| Dashboard V2.1 | Complete locally | Read-only Streamlit research cockpit implemented and smoke-tested. |
| M4 | Not started | Matched-control contract/engine is the next permitted engineering task. |
| H03 | Blocked | `BLOCKED_NO_CALENDAR_DATA`; authorized historical calendar data is absent. |

## Latest verified local checkpoint

- H01: `G3_H01_COHERENT_REPRICING_V2`.
- H02: `G3_H02_BREAK_STATE_V3`.
- H03: not materialized.
- Causal event schema: `gen3-causal-event/v1`.
- Dashboard V2.1: read-only; no raw market or outcome computation.
- Test environment: Python virtual environment with pytest 9.1.1.
- Latest reported full suite: **111 passed, 2 skipped, 13 subtests passed**.
- Focused Dashboard V2.1 suite: **5 passed**.
- Compile check for `dashboard` and `engine/gen3`: passed.
- Streamlit smoke test: HTTP 200.

These results describe the verified local workstation checkpoint. They are not yet reproducible from the public `main` branch because the corresponding M0-M3B and Dashboard V2.1 source files have not been synchronized to GitHub.

## Public GitHub synchronization state

As of 20 August 2026:

- GitHub `main` still contains the earlier public research-platform snapshot.
- `engine/gen3/events.py`, `tests/test_gen3_events.py` and the Dashboard V2.1 modules are not present on `main`.
- The previous README value of 73 passing tests describes an older checkpoint.
- This documentation update does not recreate missing source code from summaries.
- Broker-derived ticks, bars, Parquet datasets, credentials and generated research artifacts remain excluded from GitHub.

Before claiming that GitHub contains M3B, the exact current local source tree must be synchronized and reviewed for secrets, broker-derived data and generated artifacts. CI must then reproduce the tests from the uploaded code.

## Data checkpoint

The verified local EUR/USD research history previously recorded:

- 51,949,422 ticks;
- 519 `COMPLETED` daily chunks;
- 208 `EXPECTED_MARKET_CLOSED` chunks;
- 3 `NO_BROKER_HISTORY` chunks;
- monthly M5/M15/H1 partitions for the research scope.

Chronological roles remain:

```text
before 2025-08-01              -> DISCOVERY
2025-08-01 through 2026-02-01  -> CONFIRMATION
2026-02-01 through 2026-08-01  -> LOCKED_HOLDOUT
```

The locked holdout must not be opened to tune Gen-3.

## What the project has achieved

1. It has built a serious deterministic research and validation infrastructure.
2. It has preserved negative Gen-1 and Gen-2 evidence instead of optimizing it away.
3. It has moved Gen-3 from generic candle signals toward causal event/process hypotheses.
4. It has preregistered H01/H02 and implemented their causal materializers locally.
5. It has maintained the research firewall: no live execution, no AI-generated direction and no Gen-3 outcome inspection.

## What has not been achieved

- No statistically confirmed Gen-3 effect.
- No economically meaningful Gen-3 effect.
- No positive net OOS alpha.
- No paper-eligible strategy.
- No production trading system.
- No evidence that H01 or H02 survives matched controls.

## Next permitted work

1. Synchronize the exact local M0-M3B and Dashboard V2.1 source code to a review branch.
2. Verify the Git diff excludes data, artifacts, credentials and secrets.
3. Run GitHub CI and reconcile it with the local 111-test checkpoint.
4. Audit or freeze the full matched-control contract.
5. Implement M4 without materializing outcomes or touching the locked holdout.

Only after event materialization on an authorized non-holdout role, matched controls and forward outcome analysis may the project evaluate whether H01/H02 contain incremental information.