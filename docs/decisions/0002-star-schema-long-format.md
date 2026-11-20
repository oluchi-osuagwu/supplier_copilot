# ADR 0002: Long-format star schema for sales data

**Status:** Accepted (Week 1)

## Context
Raw M5 sales are wide: one row per item-store, one column per day. Questions are about
time ranges, categories, stores, and revenue.

## Decision
Unpivot to long format (one row per item × store × day) and model it as a star schema:
`fact_sales`, `fact_prices` + `dim_item`, `dim_store`, `dim_date`, plus the view `v_daily_sales`.

## Why
- **Long format:** "sales in Q3" becomes `WHERE date BETWEEN ...` instead of listing 92 column names.
- **Star schema:** the standard analytics model. Facts hold measures, dimensions hold the
  hierarchy (cat → dept → item, state → store). It is easy for humans and for an LLM
  writing SQL (week 3) to understand.
- **The view** hides joins and computes revenue, so the text-to-SQL agent has fewer ways to be wrong.
- **Facts sorted by date:** DuckDB's per-block min/max stats (zone maps) let date-filtered
  queries skip irrelevant data.

## Constraints and data quality
PKs are declared on dimensions only. On the 59M-row fact table, uniqueness and referential
integrity are enforced by tests (`tests/test_data_quality.py`), not indexes, as in most
cloud warehouses.

## Observed
12.3M sales rows have no price. All have `units_sold = 0`, meaning the item wasn't stocked yet
("structural zeros", not zero demand). This matters for anomaly detection in phase 2.
