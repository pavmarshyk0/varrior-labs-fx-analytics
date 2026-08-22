[English](README.md) | **Українська** | [Polski](README.pl.md)

# Varrior Labs FX Analytics

[![CI](https://github.com/pavmarshyk0/varrior-labs-fx-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/pavmarshyk0/varrior-labs-fx-analytics/actions/workflows/ci.yml)

Детермінована платформа кількісних досліджень EUR/USD для фальсифікованого пошуку alpha, валідації без витоку даних, тестування з урахуванням витрат виконання та експериментів лише в paper-режимі.

> **Лише дослідницьке ПЗ.** Жодних заяв про прибутковість, жодного live execution і жодних фінансових порад.

## Статус

| Покоління | Статус | Результат |
|---|---|---|
| Gen-1 | `NO_EDGE_FOUND` | Початкові сімейства momentum / pullback / breakout не змогли підтвердити стійке позитивне OOS-маточікування. |
| Gen-2 | `NO_EDGE_FOUND_GEN2` | Діагностика не виявила стабільного pre-entry сигналу, достатньо сильного для promotion. |
| Gen-3 | `RESEARCH_IN_PROGRESS` | Матеріалізатори H01 V2/H02 V3 і Dashboard V2.1 перевірені локально; Gen-3 outcomes ще не обчислювалися. |

```text
TRADABLE_EDGE: NOT ESTABLISHED
LIVE_EXECUTION: DISABLED
AI_ALPHA_GENERATION: DISABLED
```

> **Статус синхронізації репозиторію (22 серпня 2026):** ця гілка містить перевірений source tree M3B і Dashboard V2.1. Gen-3 events, matched controls та outcomes не запускалися; `main` не зміниться до review і merge draft pull request. Детальний статус: [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md).

Основна мета — **позитивне та стійке net out-of-sample маточікування після реалістичних витрат виконання**.

## Навіщо існує цей проєкт

Багато торгових проєктів оптимізують параметри, доки історична equity curve не починає виглядати привабливо. Цей проєкт навмисно побудований так, щоб слабкі ідеї провалювалися рано і прозоро.

Канонічна послідовність дослідження:

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

Відхилена гіпотеза — це валідний результат дослідження.

## Архітектура

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

## Реалізована інфраструктура

- збір історичних tick-даних MetaTrader 5 лише через `copy_ticks_range`;
- UTC-first валідація tick-даних без прихованого очищення аномалій;
- resumable Parquet storage з lineage metadata;
- детерміноване формування M5 / M15 / H1 bars;
- діагностика spread, gaps та tick density;
- backtesting досліджень на executable bid/ask;
- gross/net R та явне розкладання transaction costs;
- volatility-, event- та joint-execution stress scenarios;
- structural invalidation та кілька research exit policies;
- purged chronological walk-forward validation з embargo;
- block-bootstrap confidence intervals та reliability tiers;
- frozen candidate universes та holdout infrastructure;
- deterministic alpha-family benchmarking і Gen-2 failure diagnostics;
- локальний read-only Streamlit research dashboard;
- автоматизовані тести та GitHub CodeQL scanning.

Дані брокера та згенеровані дослідницькі артефакти навмисно виключені з публічного source tree. Див. [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).

## Поточний етап розширеної історії

Перевірена локальна історія EUR/USD зараз охоплює **2024-08 — 2026-08**:

- 51,949,422 ticks;
- 519 daily chunks зі статусом `COMPLETED`;
- 208 chunks `EXPECTED_MARKET_CLOSED`;
- 3 chunks `NO_BROKER_HISTORY`;
- monthly M5/M15/H1 partitions побудовані для всього research scope.

Перше session-open дослідження із locked protocol використовує:

- discovery: до `2025-08-01`;
- confirmation: `2025-08-01 → 2026-02-01`;
- final holdout: `2026-02-01 → 2026-08-01`, статус `LOCKED`.

Безумовні ефекти London open та New York open змінили знак між discovery і confirmation. Жоден не був promoted, на їх основі не створено Gen-3 candidate, а результати locked holdout залишаються необчисленими.

Останній перевірений локальний checkpoint: **111 passed, 2 skipped, 13 subtests passed**. Ця гілка містить відповідний source M3B/Dashboard V2.1; GitHub CI ще має відтворити результат перед merge.

## Що показали перші експерименти

Перші детерміновані сімейства **не** продемонстрували стійкого alpha. Замість тюнінгу до моменту, поки backtest не стане зеленим, проєкт зберіг негативні докази й змінив сам об'єкт дослідження.

Поточні канонічні висновки:

```text
GEN-1: NO_EDGE_FOUND
GEN-2: NO_EDGE_FOUND_GEN2
GEN-3: RESEARCH_IN_PROGRESS
```

Тому публічний репозиторій представляє **research and validation platform**, а не готову торгову стратегію.

## Gen-3 Tier A research

### `G3_H01_COHERENT_REPRICING`

Перевіряє, чи додають short-horizon quote-process features інкрементальну directional information **понад matched price impulse**.

Кандидатні observables включають:

- directional bid/ask quote revisions;
- synchronous bid/ask movement;
- tick-arrival intensity та inter-arrival times;
- spread state та spread transition;
- path efficiency;
- short-window realized volatility.

Ключове дослідницьке питання:

> Чи перевершує coherent repricing event інший подібний price impulse, matched за direction, magnitude, session, volatility та spread context?

### `G3_H02_BREAK_STATE`

Розглядає взаємодію з рівнем як один price-discovery process:

```text
BREAK
 ├── ACCEPT  → continuation distribution
 └── REJECT  → reversal distribution
```

PDH/PDL, Asian highs/lows та local extrema трактуються як **level generators**, а не як припущене самостійне alpha. Named level має перевершити matched generic extrema, щоб продемонструвати incremental information.

### `G3_H03_MACRO_HAZARD`

Детермінований execution-risk/context layer для scheduled macro events, а не directional alpha source за замовчуванням.

Основні застосування:

- expected volatility hazard;
- spread/slippage regime tagging;
- NO_TRADE research;
- post-event price-discovery context.

## Governance

Проєкт дотримується кількох незмінних правил:

- жодної look-ahead information у candidate generation;
- жодного random train/test split для time-series validation;
- жодного tuning на final holdout;
- суттєві зміни гіпотези рахуються як нові research trials;
- transaction costs є частиною економіки гіпотези;
- statistical significance недостатньо: ефект також має пройти economic execution hurdle;
- жодного martingale, grid або averaging-down logic;
- жодного executable `MetaTrader5.order_send` path у research pipeline.

Універсальний gate `RR >= 3` **не** є поточною метою дослідження. Fixed 3R залишається frozen control там, де це корисно; research decisions визначають structural invalidation та net expectancy.

Канонічний protocol див. у [`docs/RESEARCH_GOVERNANCE.md`](docs/RESEARCH_GOVERNANCE.md).

## Встановлення

Потрібен Python 3.11+.

Основний research package:

```bash
python -m pip install -e .
```

Dashboard dependencies:

```bash
python -m pip install -e ".[dashboard]"
```

MetaTrader 5 integration на Windows:

```bash
python -m pip install -e ".[mt5]"
```

Повна локальна конфігурація workstation на Windows:

```bash
python -m pip install -e ".[dashboard,mt5]"
```

## Тести

```bash
python -m unittest discover -s tests -v
```

GitHub CI запускає suite на Python 3.11 та 3.12.

## Dashboard

Dashboard читає лише локальні precomputed research artifacts:

```bash
Start_Varrior_Dashboard.bat
# або: python -m streamlit run dashboard/app.py
```

Публічний репозиторій навмисно не містить broker-derived datasets, необхідних для наповнення dashboard. Після запуску research pipeline вкажіть у sidebar локальну директорію `data/research/alpha/latest`.

## Корисні CLI-приклади

Перевірити експортований tick CSV:

```bash
demo-beta validate-ticks ticks.csv
```

Зібрати historical ticks із локально авторизованого MT5 terminal:

```bash
demo-beta collect-mt5-history \
  --start 2026-07-01T00:00:00Z \
  --end 2026-08-01T00:00:00Z \
  --output-dir data/processed/mt5 \
  --chunk-hours 24 \
  --symbol EURUSD
```

Запустити frozen exit-policy research control:

```bash
demo-beta run-exit-ablation \
  --bars-dir data/processed/bars/EURUSD \
  --output-dir data/research/latest \
  --minimum-train-size 20 \
  --validation-size 15 \
  --candidate-stride-bars 12 \
  --max-holding-bars 36
```

Ці команди створюють лише research artifacts. Вони не розміщують live orders.

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

## Політика репозиторію

Перед внесенням змін прочитайте:

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

## Філософія проєкту

Мета — не максимізувати історичну backtest performance. Мета — знайти докази, які витримують falsification, independent confirmation та realistic execution costs до того, як у процес залучається капітал.

## Ліцензія

Copyright © 2026 Paweł Maruszczyk. All rights reserved.

Цей репозиторій є **source-available, а не open source**. Перегляд для оцінювання дозволений, але будь-яке використання, копіювання, модифікація, розповсюдження, deployment, derivative work або commercial/non-commercial exploitation потребує попереднього письмового дозволу та окремої угоди. Див. [`LICENSE`](LICENSE).
