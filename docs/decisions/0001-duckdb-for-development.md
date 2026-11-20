# ADR 0001: DuckDB as the development warehouse

**Status:** Accepted (Week 1)

## Context
The M5 sales file is wide (1,941 day columns). Converting it to long format gives ~59M rows.
We need fast analytical SQL (group-bys, date filters) locally, with no server to run.

## Decision
Use DuckDB, an embedded (in-process, single-file) columnar OLAP database, for development.
Postgres will be used at deployment (week 8) because it also hosts pgvector.

## Why
- **Columnar + vectorized:** reads only the columns a query needs and processes values in
  batches, so aggregations over 59M rows take seconds.
- **No server:** the database is one file, `data/processed/supplier_copilot.duckdb`.
- **Reads CSV natively** and supports `UNPIVOT`, so the transform runs in SQL (ELT).
- pandas would hold ~59M rows as in-memory objects (multiple GB) and run single-threaded.

## Trade-offs
- Single writer at a time, which is fine for a batch pipeline but not for a multi-user API.
  That's why Postgres is used at deployment.
- All DB access goes through `db/duckdb_client.py`, which keeps the swap contained.

## Measured
Full build: ~97 s on a 16 GB / 8-core laptop. 325 MB of CSVs became a 245 MB database.
