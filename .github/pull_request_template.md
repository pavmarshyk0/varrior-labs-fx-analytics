## Summary

Describe what changed and why.

## Research / engineering classification

- [ ] Infrastructure / developer ergonomics
- [ ] Data quality / lineage
- [ ] Research hypothesis or feature definition
- [ ] Validation / statistics
- [ ] Execution-cost modelling
- [ ] Dashboard / documentation

## Checklist

- [ ] No broker-derived bulk data, generated Parquet datasets, credentials, or secrets are included.
- [ ] No live-order execution path is introduced.
- [ ] No martingale, grid, or averaging-down behavior is introduced.
- [ ] Candidate-generation changes use information available at event time only.
- [ ] Material hypothesis changes have a new hypothesis/version ID and preregistered controls.
- [ ] New or changed behavior has tests where practical.
- [ ] `python -m unittest discover -s tests -v` passes locally.
- [ ] Documentation reflects any governance or public-interface change.
- [ ] No unconfirmed result is described as profitable alpha.

## Validation

List the commands/tests run and the result.

## Research impact

If applicable, state the dataset role affected (`DISCOVERY`, `CONFIRMATION`, `SECONDARY_OOS`, `FORWARD_HOLDOUT`) and whether the change increases the effective research trial count.
