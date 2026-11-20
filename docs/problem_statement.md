# Problem Statement

## The user (persona)

**Maya, Senior Category Analyst at "Harvest Lane Foods"**, a simulated mid-sized packaged-food
manufacturer that sells through a large US mass retailer in California, Texas, and Wisconsin.

M5 product names are anonymized, so the persona is defined to fit the data:
Harvest Lane's portfolio **is the `FOODS_3` department** (823 items, the retailer's largest food
department). `FOODS_1` and `FOODS_2` act as adjacent food departments, and `HOBBIES` /
`HOUSEHOLD` as the rest of the store. Harvest Lane and Maya are fictional.

## The decisions Maya has to make

Every quarter Maya prepares for a business review with the retailer's category team. She has
to:

1. **Explain performance:** what changed (units, revenue, price), where (state, store), and when.
2. **Benchmark:** is the change specific to her portfolio, or is the whole category or market
   moving the same way?
3. **Find the "why":** link movements to causes such as pricing, holidays/events, SNAP benefit
   timing, or macro trends that retailers and CPG peers describe in public filings.
4. **Recommend actions:** pricing, promotion timing, assortment, and regional focus.

## Why dashboards alone fall short

- A dashboard shows **what** happened, but not **why**. The "why" is in unstructured text:
  10-K risk factors, earnings releases, and management commentary about consumer behaviour,
  food inflation, and competition.
- Answering one question means **joining two worlds by hand**: run a query, then search
  hundreds of pages of filings for the matching period, then reconcile **fiscal years**
  (Walmart's FY2016 = Feb 2015 to Jan 2016) with calendar dates.
- Analysts spend most of their prep time gathering evidence instead of interpreting it.

### A concrete example from the data

In 2015, `FOODS_3` units fell **5.3%** year over year (6.57M to 6.22M) while the average price
paid per unit rose **4.7%** ($2.24 to $2.35), so revenue was roughly flat ($14.74M to $14.62M).
Over the same year, `FOODS_1` and `FOODS_2` revenue grew. A dashboard can show this. It can't
tell Maya whether the drop came from price elasticity, product mix, or a market-wide trend that
retailers mentioned in their filings. Answering that is the copilot's job.

## The solution

A copilot that answers natural-language questions by **routing** each question to the right
tool:

| Route | Tool | Source |
|---|---|---|
| `sql` | Text-to-SQL (read-only) | M5 warehouse: sales, prices, calendar (DuckDB star schema) |
| `docs` | Hybrid retrieval (BM25 + dense + reranker) | SEC 10-Ks and 8-K earnings releases, FY2011-2016 |
| `both` | SQL + retrieval, combined in one answer | Both of the above |

Every answer **cites its evidence**: the SQL query and its result, plus document, section, and
date for every text claim. When there isn't enough evidence, the copilot **says so** instead of
guessing.

## Scope

**In scope (Phase 1):** questions about M5 sales/prices/events from 2011-01-29 to 2016-05-22,
plus public filings from WMT, TGT, KR, COST (retailers) and PG, PEP, GIS (CPG peers) covering the
same period.

**Out of scope:** forecasting future sales, real-time data, competitor store-level data, and any
non-public or employer data. Phase 2 adds anomaly detection and external events (recalls,
weather, news).

## What success looks like

Measured on the gold question set (`eval/questions/`), growing from the 20 starter questions to
60-100:

| Metric | What it measures | Initial target |
|---|---|---|
| Routing accuracy | Picked the right route (`sql` / `docs` / `both` / refuse) | ≥ 90% |
| SQL execution accuracy | Query result matches the expected answer | ≥ 85% |
| Retrieval recall@5 | The relevant passage is in the top 5 results | ≥ 80% |
| Faithfulness | Answer claims are supported by retrieved evidence | ≥ 0.85 |
| Correct refusals | Out-of-scope questions are declined, not invented | 100% |
| Latency (p95) / cost | Per question, tracked in Langfuse | < 10 s / < $0.02 |

These targets are a starting point and will be revised once a baseline is measured.

## Known limitations

- M5 is historical (ends May 2016), covers only 10 stores in 3 states, and is anonymized.
- The persona and questions are simulated, not from real suppliers.
- The SEC filings describe whole companies, not these 10 stores, so they give market context,
  not store-level causes.
- "Average price paid" mixes real price changes with product-mix shifts. The copilot has to
  explain this, not hide it.
