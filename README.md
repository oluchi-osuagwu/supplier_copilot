# Supplier Insights Copilot

A RAG assistant for retail suppliers. It answers questions like *"Why did my snack category
drop in Q3, and how do I compare to the market?"* by routing between:

- **Text-to-SQL** over structured sales data (M5 / Walmart, in a DuckDB star schema)
- **Hybrid document retrieval** (BM25 + dense embeddings + reranker) over SEC 10-Ks and earnings calls

Phase 2 extends it into an **Anomaly Explainer** (Bollinger Band anomalies + external events retrieval).

> Built only on public data. The "supplier" is a simulated persona. No employer data, tools, or methods.

## Status

| Week | Focus | Status |
|---|---|---|
| 1 | Scaffold, M5 warehouse, downloaders, problem statement | In progress (warehouse, problem statement, 20 questions done; SEC downloader next) |
| 2 | Document pipeline | – |
| 3 | Text-to-SQL | – |
| 4 | Hybrid retrieval | – |
| 5 | Agentic routing | – |
| 6 | Evaluation | – |
| 7 | API + UI + observability | – |
| 8 | Deployment | – |

## Setup (Windows / PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env      # then fill in values
```

### Data

M5 data can't be redistributed under Kaggle's terms, so it is not in this repo.

1. Accept the rules at <https://www.kaggle.com/c/m5-forecasting-accuracy> and download the data.
2. Put `calendar.csv`, `sales_train_evaluation.csv`, `sell_prices.csv` in `data/raw/m5/`.

### Build the warehouse and test it

```powershell
python scripts/run_ingestion.py   # ~1.5 min: CSVs -> data/processed/supplier_copilot.duckdb
pytest                            # unit tests + data-quality tests
ruff check .                      # lint
```

## Data model (star schema)

| Table | Grain (one row = …) | Rows |
|---|---|---|
| `fact_sales` | item × store × day | 59,181,090 |
| `fact_prices` | item × store × fiscal week | 6,841,121 |
| `dim_item` | item (cat → dept → item) | 3,049 |
| `dim_store` | store (state → store) | 10 |
| `dim_date` | day (events, SNAP flags, fiscal week) | 1,969 |
| `v_daily_sales` | view: sales + hierarchy + price + revenue | – |

## Project layout

```
configs/      settings.yaml (non-secret config)
data/         raw -> interim -> processed (gitignored)
docs/         problem statement, architecture, decision records (ADRs)
eval/         gold question sets and evaluation
scripts/      entry points (run_ingestion.py)
src/supplier_copilot/
  config.py, logging_setup.py
  db/          schema.sql, DuckDB client
  ingestion/   M5 loader, SEC + transcript downloaders
  retrieval/   (week 2, 4)   agents/ (week 5)   api/ (week 7)
tests/        unit tests (synthetic data) + data-quality tests (real warehouse)
```

## Limitations

- M5 ends in May 2016 and covers 10 stores in 3 states, so it is not current market data.
- The supplier persona and questions are simulated.
