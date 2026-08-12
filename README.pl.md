[English](README.md) | [Українська](README.uk.md) | **Polski**

# Varrior Labs FX Analytics

[![CI](https://github.com/pavmarshyk0/varrior-labs-fx-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/pavmarshyk0/varrior-labs-fx-analytics/actions/workflows/ci.yml)

Deterministyczna platforma badań ilościowych EUR/USD do falsyfikowalnego odkrywania alpha, walidacji odpornej na leakage, testów uwzględniających koszty wykonania oraz eksperymentów wyłącznie w trybie paper.

> **Wyłącznie oprogramowanie badawcze.** Bez deklaracji rentowności, bez live execution i bez porad finansowych.

## Status

| Generacja | Status | Wynik |
|---|---|---|
| Gen-1 | `NO_EDGE_FOUND` | Początkowe rodziny momentum / pullback / breakout nie wykazały stabilnej dodatniej oczekiwanej wartości OOS. |
| Gen-2 | `NO_EDGE_FOUND_GEN2` | Diagnostyka nie znalazła stabilnego sygnału pre-entry wystarczająco silnego do promotion. |
| Gen-3 | `RESEARCH_IN_PROGRESS` | Badania event-time price discovery, matched controls i krótkoterminowej mikrostruktury rynku. |

```text
TRADABLE_EDGE: NOT ESTABLISHED
LIVE_EXECUTION: DISABLED
AI_ALPHA_GENERATION: DISABLED
```

Głównym celem jest **dodatnia i stabilna net out-of-sample expectancy po realistycznych kosztach wykonania**.

## Dlaczego ten projekt istnieje

Wiele projektów tradingowych optymalizuje parametry tak długo, aż historyczna equity curve zacznie wyglądać atrakcyjnie. Ten projekt został celowo zaprojektowany tak, aby słabe pomysły odpadały wcześnie i w sposób widoczny.

Kanoniczna sekwencja badawcza:

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

Odrzucona hipoteza jest prawidłowym wynikiem badania.

## Architektura

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

## Zaimplementowana infrastruktura

- zbieranie historycznych ticków MetaTrader 5 wyłącznie przez `copy_ticks_range`;
- walidacja ticków w podejściu UTC-first bez ukrytego czyszczenia anomalii;
- wznawialne przechowywanie Parquet z metadanymi lineage;
- deterministyczna budowa barów M5 / M15 / H1;
- diagnostyka spreadu, luk i gęstości ticków;
- backtesting badań na executable bid/ask;
- gross/net R i jawna dekompozycja kosztów transakcyjnych;
- scenariusze volatility-, event- i joint-execution stress;
- structural invalidation oraz wiele polityk research exit;
- purged chronological walk-forward validation z embargo;
- block-bootstrap confidence intervals i reliability tiers;
- frozen candidate universes i infrastruktura holdout;
- deterministic alpha-family benchmarking oraz diagnostyka porażek Gen-2;
- lokalny read-only dashboard badawczy w Streamlit;
- testy automatyczne i skanowanie GitHub CodeQL.

Dane pochodzące od brokera oraz generowane artefakty badawcze są celowo wyłączone z publicznego source tree. Zobacz [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).

## Aktualny etap rozszerzonej historii

Zweryfikowana lokalna historia EUR/USD obejmuje obecnie **2024-08 — 2026-08**:

- 51,949,422 ticków;
- 519 dziennych chunków `COMPLETED`;
- 208 chunków `EXPECTED_MARKET_CLOSED`;
- 3 chunki `NO_BROKER_HISTORY`;
- miesięczne partycje M5/M15/H1 zbudowane dla pełnego zakresu badawczego.

Pierwsze badanie session-open z locked protocol wykorzystuje:

- discovery: przed `2025-08-01`;
- confirmation: `2025-08-01 → 2026-02-01`;
- final holdout: `2026-02-01 → 2026-08-01`, status `LOCKED`.

Bezwarunkowe efekty London open i New York open zmieniły znak między discovery a confirmation. Żaden z nich nie został promoted, nie utworzono na ich podstawie Gen-3 candidate, a wyniki locked holdout pozostają nieobliczone.

Ostatnia zweryfikowana lokalna walidacja: **73 tests passed**.

## Co pokazały pierwsze eksperymenty

Pierwsze rodziny deterministyczne **nie** wykazały stabilnego alpha. Zamiast stroić je do momentu, aż backtest stanie się zielony, projekt zachował negatywne dowody i zmienił sam obiekt badania.

Aktualne kanoniczne wnioski:

```text
GEN-1: NO_EDGE_FOUND
GEN-2: NO_EDGE_FOUND_GEN2
GEN-3: RESEARCH_IN_PROGRESS
```

Publiczne repozytorium reprezentuje więc **platformę badawczą i walidacyjną**, a nie gotową strategię tradingową.

## Gen-3 Tier A research

### `G3_H01_COHERENT_REPRICING`

Sprawdza, czy krótkoterminowe quote-process features dodają inkrementalną informację kierunkową **ponad matched price impulse**.

Kandydackie obserwable obejmują:

- directional bid/ask quote revisions;
- synchronous bid/ask movement;
- tick-arrival intensity i inter-arrival times;
- spread state i spread transition;
- path efficiency;
- short-window realized volatility.

Kluczowe pytanie badawcze:

> Czy coherent repricing event przewyższa podobny price impulse matched pod względem direction, magnitude, session, volatility i spread context?

### `G3_H02_BREAK_STATE`

Traktuje interakcję z poziomem jako jeden proces price discovery:

```text
BREAK
 ├── ACCEPT  → continuation distribution
 └── REJECT  → reversal distribution
```

PDH/PDL, Asian highs/lows oraz local extrema są traktowane jako **level generators**, a nie jako z góry przyjęte samodzielne alpha. Named level musi przewyższyć matched generic extrema, aby wykazać incremental information.

### `G3_H03_MACRO_HAZARD`

Deterministyczna warstwa execution-risk/context dla scheduled macro events, a nie domyślne źródło directional alpha.

Główne zastosowania:

- expected volatility hazard;
- spread/slippage regime tagging;
- NO_TRADE research;
- post-event price-discovery context.

## Governance

Projekt przestrzega kilku niepodlegających negocjacji zasad:

- brak look-ahead information w candidate generation;
- brak random train/test split dla walidacji time-series;
- brak tuningu na final holdout;
- istotne zmiany hipotezy liczą się jako nowe research trials;
- koszty transakcyjne są częścią ekonomiki hipotezy;
- sama statistical significance nie wystarcza: efekt musi również przejść economic execution hurdle;
- brak martingale, grid i averaging-down logic;
- brak wykonywalnej ścieżki `MetaTrader5.order_send` w research pipeline.

Uniwersalny gate `RR >= 3` **nie** jest obecnym celem badawczym. Fixed 3R pozostaje frozen control tam, gdzie ma to sens; decyzje badawcze wynikają ze structural invalidation i net expectancy.

Kanoniczny protokół znajduje się w [`docs/RESEARCH_GOVERNANCE.md`](docs/RESEARCH_GOVERNANCE.md).

## Instalacja

Wymagany jest Python 3.11+.

Główny pakiet badawczy:

```bash
python -m pip install -e .
```

Zależności dashboardu:

```bash
python -m pip install -e ".[dashboard]"
```

Integracja MetaTrader 5 na Windows:

```bash
python -m pip install -e ".[mt5]"
```

Pełna lokalna konfiguracja workstation na Windows:

```bash
python -m pip install -e ".[dashboard,mt5]"
```

## Testy

```bash
python -m unittest discover -s tests -v
```

GitHub CI uruchamia suite na Python 3.11 i 3.12.

## Dashboard

Dashboard odczytuje wyłącznie lokalne precomputed research artifacts:

```bash
python -m streamlit run app.py
```

Publiczne repozytorium celowo nie zawiera broker-derived datasets wymaganych do zasilenia dashboardu. Po uruchomieniu research pipeline wskaż w sidebar lokalny katalog `data/research/alpha/latest`.

## Przydatne przykłady CLI

Walidacja wyeksportowanego tick CSV:

```bash
demo-beta validate-ticks ticks.csv
```

Zbieranie historycznych ticków z lokalnie zalogowanego terminala MT5:

```bash
demo-beta collect-mt5-history \
  --start 2026-07-01T00:00:00Z \
  --end 2026-08-01T00:00:00Z \
  --output-dir data/processed/mt5 \
  --chunk-hours 24 \
  --symbol EURUSD
```

Uruchomienie frozen exit-policy research control:

```bash
demo-beta run-exit-ablation \
  --bars-dir data/processed/bars/EURUSD \
  --output-dir data/research/latest \
  --minimum-train-size 20 \
  --validation-size 15 \
  --candidate-stride-bars 12 \
  --max-holding-bars 36
```

Te polecenia generują wyłącznie research artifacts. Nie składają live orders.

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

## Polityka repozytorium

Przed wniesieniem zmian przeczytaj:

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

## Filozofia projektu

Celem nie jest maksymalizacja historycznej wydajności backtestu. Celem jest znalezienie dowodów, które przetrwają falsification, independent confirmation i realistic execution costs, zanim w proces zostanie zaangażowany kapitał.

## Licencja

Copyright © 2026 Paweł Maruszczyk. All rights reserved.

To repozytorium jest **source-available, a nie open source**. Przeglądanie w celu oceny jest dozwolone, ale jakiekolwiek użycie, kopiowanie, modyfikowanie, dystrybucja, deployment, derivative work lub commercial/non-commercial exploitation wymaga uprzedniej pisemnej zgody i osobnej umowy. Zobacz [`LICENSE`](LICENSE).
