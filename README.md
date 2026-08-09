# EUR/USD demo-0.0-beta

Deterministic research core for EUR/USD intraday candidate filtering. This is research/paper-trading software, not a profitability claim and not a live execution system.

## Implemented through milestone M5 (research extension)

- strict domain contracts for ticks and candidates;
- fixed-3R control baseline and hard risk <= 1% gate;
- MT5-compatible tick validation without silently cleaning anomalies;
- optional MT5 tick collector adapter;
- CSV tick ingestion;
- executable bid/ask triple-barrier backtester;
- deterministic slippage, latency and missed-fill stress hooks;
- gross/net R and explicit spread/slippage cost decomposition;
- conservative `AMBIGUOUS` handling for conflicting same-timestamp barrier evidence;
- CLI and automated tests.
- standardized secondary-module output envelope that cannot change direction;
- DST-aware market clocks and benchmark-window context;
- versioned economic-calendar snapshots with an anti-leakage guard;
- scheduled high-impact macro hard veto with explicit research-only window parameters.
- architecture-compatible `data_ingestion/`, `analytics/` and `engine/` packages;
- validated UTC Parquet export path (PyArrow);
- tick-state SHADOW classifier with session median/MAD baselines, formal level
  excursion detection and quote-pressure proxy features;
- Hawkes-inspired decayed burst intensity as a research feature only;
- hierarchical temporal posterior table with sparse-bucket shrinkage;
- BOCPD volatility/liquidity guard in SHADOW mode plus a simpler median/MAD
  comparator it must beat before promotion;
- research-only duration-constrained HSMM baseline;
- chronological purged walk-forward split engine with embargo;
- meta-label/conformal infrastructure with an executable bid/ask triple-barrier
  bridge and a hard minimum of 800 candidates before fitting;
- YAML baseline/execution configuration and deterministic unit tests.
- strict JSON calendar snapshots and observed-only post-jump research inputs;
- resumable MT5 -> validation -> Parquet chunks with immutable lineage sidecars;
- fold-local session baselines, OOS statistics, block-bootstrap 95% CIs,
  frozen ablations, and a lineage-aware Markdown report renderer.
- configurable execution-cost estimates and non-independent joint execution-stress scenarios;
- structural invalidations, deterministic target selection and fixed/dynamic/structure/partial exit plans;
- path-aware target-before-stop probabilities, reliability tiers and deterministic shrinkage;
- net-EV feasibility gates, normalized weighted ranking, locked final-holdout and live-micro pause interfaces.

## Run

Python 3.11+ is required.

```bash
python -m pip install -e .
PYTHONPATH=src python -m unittest discover -s tests -v
```

Validate an exported tick CSV (`time_msc,bid,ask,flags`):

```bash
demo-beta validate-ticks ticks.csv
```

Collect historical ticks from a locally logged-in MT5 terminal. This only calls
`copy_ticks_range`; it never calls `order_send`:

```bash
demo-beta collect-mt5-history --start 2024-01-01T00:00:00Z --end 2024-02-01T00:00:00Z --output-dir data/processed/mt5 --chunk-hours 24 --symbol EURUSD
```

Backtest one candidate:

```bash
demo-beta backtest --candidate candidate.json --ticks ticks.csv
```

Run the frozen, research-only exit-policy ablation over built EUR/USD bars:

```bash
demo-beta run-exit-ablation --bars-dir data/processed/bars/EURUSD --output-dir data/research/latest \
  --minimum-train-size 20 --validation-size 15 --candidate-stride-bars 12 --max-holding-bars 36
```

This command freezes one candidate universe before evaluating all exit-policy
arms. It writes dashboard-ready `summary.json`, a detailed Parquet result set,
and a Markdown report. It does not call `order_send` or otherwise execute an
order.

Candidate JSON uses UTC ISO-8601 timestamps:

```json
{
  "candidate_id": "example-001",
  "direction": "LONG",
  "entry": 1.15162,
  "stop_loss": 1.15092,
  "take_profit": 1.15372,
  "entry_available_at": "2026-08-05T09:15:00Z",
  "max_holding_minutes": 90,
  "risk_fraction": 0.005
}
```

The legacy backtester retains the frozen fixed-3R/risk control gate.  New
research exit policies are assessed by structural validity, risk, net OOS EV,
stress survival and sample reliability; they do not authorise live trading.

## Safety status

- `tick_state_classifier`: **SHADOW** — logs/supports research, not a production claim.
- `online_regime_guard`: **SHADOW** — suggested risk changes are logged, applied
  multiplier remains 1.0.
- `hsmm_regime_filter`: **RESEARCH** — cannot veto.
- `tick_burst_intensity`: **RESEARCH feature** — no standalone weight.
- `meta_label_conformal`: **DISABLED_UNTIL_SAMPLE** — cannot fit below 800 candidates.

## Next milestone

1. Obtain historical EUR/USD ticks and immutable calendar snapshots.
2. Build a real candidate-event OOS experiment family and run the frozen M4 report.
3. Add DSR/PBO/SPA only after the baseline candidate generator produces a
   real experiment family and enough OOS observations.

See `docs/HANDOFF.md` for the exact continuation point.
