# Security Policy

## Scope

Varrior Labs FX Analytics is research/paper-only software. The repository is intentionally designed without a live `MetaTrader5.order_send` execution path. Security issues can still matter because local research workstations may contain broker terminals, market data, credentials, and generated artifacts.

## Reporting a vulnerability

Please report security-sensitive findings privately using GitHub's private vulnerability reporting / Security Advisory flow when available for this repository. If private reporting is not available, contact the repository owner through their GitHub profile before disclosing sensitive details publicly.

Do **not** open a public issue containing credentials, tokens, private keys, account identifiers, broker connection details, or exploit instructions that expose a user's local environment.

## Secret handling

The repository must not contain:

- broker credentials;
- API tokens;
- `.env` files;
- private keys or certificates;
- Streamlit secrets;
- personally identifying trading-account information.

If a secret is committed accidentally, treat it as compromised: revoke/rotate it first, then remove it from the repository and, if necessary, rewrite history.

## Supported state

Security fixes target the current `main` branch. Historical research snapshots are not separately supported.

## Trading safety boundary

A change that introduces live execution, automated capital deployment, credential persistence, or remote order-control capabilities is a material security and governance change and should not be merged into the current research-only architecture without an explicit redesign and review.
