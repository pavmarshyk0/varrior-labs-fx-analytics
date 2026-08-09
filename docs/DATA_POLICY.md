# Data Policy

## Principle

The public repository contains source code, configuration, documentation and small synthetic fixtures. It should not redistribute broker-derived market history or generated research datasets.

## Do not commit

- raw MetaTrader 5 tick history;
- broker-exported CSV files containing market history;
- generated M5/M15/H1 or sub-minute Parquet datasets;
- research artifacts that reproduce licensed or broker-derived datasets at material scale;
- credentials, account identifiers, terminal profiles or connection secrets;
- local databases, caches or model checkpoints.

The `.gitignore` is a convenience, not a security boundary. Always inspect staged files before pushing.

## Allowed public artifacts

The following are appropriate when they contain no sensitive or redistributable market data:

- schemas;
- code;
- small synthetic test fixtures;
- data-quality rules;
- fingerprints/hashes;
- aggregate research metrics;
- methodology documentation;
- manually curated screenshots that do not expose account information or secrets.

## Reproducibility without redistributing broker data

A reproducible experiment should record enough metadata to rebuild the result locally from an authorized data source:

- symbol and canonical timezone;
- requested collection interval;
- collection/chunk policy;
- dataset fingerprint;
- lineage status;
- build configuration;
- feature/hypothesis version;
- cost-model version;
- chronological dataset role.

## Local directory convention

Generated local data should live under ignored paths such as:

```text
data/raw/
data/processed/
data/research/
data/cache/
```

Public source code must not depend on those directories existing at import time. Dashboards and CLI commands should fail gracefully when local artifacts are absent.

## Historical cleanup

Removing a file from the current tree does not erase it from Git history. If a secret, personal identifier, or data that must not remain public was committed, use an appropriate history-rewrite procedure in addition to normal deletion.
