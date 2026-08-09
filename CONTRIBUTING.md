# Contributing

Varrior Labs FX Analytics is a research-first EUR/USD quantitative research platform. Contributions should improve reproducibility, falsifiability, data quality, statistical validation, execution modelling, or developer ergonomics without turning the repository into a profitability-marketing project.

## Local setup

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

For the local dashboard:

```bash
python -m pip install -e ".[dashboard]"
python -m streamlit run app.py
```

On a Windows research workstation with MetaTrader 5:

```bash
python -m pip install -e ".[mt5]"
```

## Pull-request expectations

Before opening a pull request:

- keep candidate generation free of look-ahead information;
- add or update deterministic tests for material behavior changes;
- document new research hypotheses and controls before inspecting outcomes;
- treat material post-result parameter changes as a new hypothesis/version;
- keep execution costs explicit rather than burying them in signal logic;
- preserve chronological validation and holdout boundaries;
- do not add live-order execution paths;
- do not add martingale, grid, or averaging-down logic;
- do not describe an unconfirmed statistical effect as profitable alpha.

## Data and secrets

Do not commit:

- raw broker tick history;
- generated Parquet research datasets;
- research outputs that contain licensed or broker-derived market data;
- `.env` files, API keys, credentials, tokens, private certificates, or Streamlit secrets;
- Python caches, virtual environments, or build metadata.

Small synthetic fixtures are preferred for tests. See `docs/DATA_POLICY.md`.

## Research changes

A new or materially revised hypothesis should define, at minimum:

- hypothesis ID and version;
- economic mechanism;
- observable event definition;
- information set available at event time;
- matched control;
- outcome horizon(s);
- dataset role;
- cost-model version;
- falsification criteria.

See `docs/RESEARCH_GOVERNANCE.md` for the canonical research protocol.

## Style

Prefer simple deterministic code over clever abstractions. Keep time handling explicit and UTC-first unless a market-session conversion is the subject being modelled. Type hints and docstrings are encouraged where they make contracts clearer.

## Scope

This repository is research software. It is not financial advice, does not claim future profitability, and is not a live execution system.
