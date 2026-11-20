"""Data-quality tests against the REAL warehouse built by scripts/run_ingestion.py.

Unit tests prove the code is correct on small inputs; these prove the actual data is
correct at full scale (row counts, uniqueness, completeness, referential integrity,
reconciliation with the source file). Skipped automatically if the DB hasn't been built
(e.g., in CI, where the Kaggle data isn't available).
"""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from supplier_copilot.config import get_settings

SETTINGS = get_settings()
DB_PATH = SETTINGS.paths.duckdb_path

# Known facts about M5 (from the dataset documentation / file inspection)
N_ITEMS, N_STORES, N_SALES_DAYS, N_CALENDAR_DAYS = 3049, 10, 1941, 1969

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="warehouse not built yet")


@pytest.fixture(scope="module")
def con():
    """One read-only connection shared by all tests in this file (scope='module')."""
    c = duckdb.connect(str(DB_PATH), read_only=True)
    yield c
    c.close()


def scalar(con, sql: str):
    return con.execute(sql).fetchone()[0]


# ---------- Completeness: expected row counts ----------

def test_dimension_counts(con):
    assert scalar(con, "SELECT COUNT(*) FROM dim_item") == N_ITEMS
    assert scalar(con, "SELECT COUNT(*) FROM dim_store") == N_STORES
    assert scalar(con, "SELECT COUNT(*) FROM dim_date") == N_CALENDAR_DAYS
    assert scalar(con, "SELECT COUNT(DISTINCT cat_id) FROM dim_item") == 3
    assert scalar(con, "SELECT COUNT(DISTINCT dept_id) FROM dim_item") == 7
    assert scalar(con, "SELECT COUNT(DISTINCT state_id) FROM dim_store") == 3


def test_fact_sales_is_complete_grid(con):
    # Every item x store x day combination is present exactly once in M5.
    assert scalar(con, "SELECT COUNT(*) FROM fact_sales") == N_ITEMS * N_STORES * N_SALES_DAYS


def test_sales_date_range(con):
    lo, hi = con.execute("SELECT MIN(date), MAX(date) FROM fact_sales").fetchone()
    assert (lo, hi) == (date(2011, 1, 29), date(2016, 5, 22))


def test_calendar_has_no_gaps(con):
    span = scalar(con, "SELECT DATEDIFF('day', MIN(date), MAX(date)) + 1 FROM dim_date")
    assert span == N_CALENDAR_DAYS


# ---------- Uniqueness: the declared grain holds ----------

def test_fact_sales_grain_is_unique(con):
    dupes = scalar(con, """
        SELECT COUNT(*) FROM (
            SELECT item_id, store_id, date FROM fact_sales GROUP BY ALL HAVING COUNT(*) > 1
        )
    """)
    assert dupes == 0


def test_fact_prices_grain_is_unique(con):
    dupes = scalar(con, """
        SELECT COUNT(*) FROM (
            SELECT item_id, store_id, wm_yr_wk FROM fact_prices GROUP BY ALL HAVING COUNT(*) > 1
        )
    """)
    assert dupes == 0


# ---------- Validity: values are in a sensible range ----------

def test_no_negative_units_or_bad_prices(con):
    assert scalar(con, "SELECT COUNT(*) FROM fact_sales WHERE units_sold < 0") == 0
    assert scalar(con, "SELECT COUNT(*) FROM fact_prices WHERE sell_price <= 0") == 0


# ---------- Referential integrity: every foreign key has a matching dimension row ----------

@pytest.mark.parametrize(
    "fact, key, dim",
    [
        ("fact_sales", "item_id", "dim_item"),
        ("fact_sales", "store_id", "dim_store"),
        ("fact_sales", "date", "dim_date"),
        ("fact_prices", "item_id", "dim_item"),
        ("fact_prices", "store_id", "dim_store"),
    ],
)
def test_referential_integrity(con, fact, key, dim):
    # ANTI JOIN returns fact rows with NO match in the dimension ("orphans"). Expect none.
    orphans = scalar(con, f"SELECT COUNT(*) FROM {fact} f ANTI JOIN {dim} d ON f.{key} = d.{key}")
    assert orphans == 0


def test_prices_join_to_calendar_weeks(con):
    orphans = scalar(con, """
        SELECT COUNT(*) FROM (SELECT DISTINCT wm_yr_wk FROM fact_prices) p
        ANTI JOIN (SELECT DISTINCT wm_yr_wk FROM dim_date) c USING (wm_yr_wk)
    """)
    assert orphans == 0


# ---------- Business rule: unpriced days never have sales ----------

def test_units_sold_only_when_item_is_priced(con):
    """No price that week = item not on the shelf yet, so units must be 0."""
    assert scalar(con, "SELECT COUNT(*) FROM v_daily_sales WHERE sell_price IS NULL AND units_sold > 0") == 0


# ---------- Reconciliation: warehouse totals match the raw source file ----------

def test_total_units_reconcile_with_raw_csv(con):
    """Sum every d_* column straight from the CSV and compare to the warehouse total."""
    sales_csv = (SETTINGS.paths.raw_m5_dir / SETTINGS.m5.sales_file).as_posix()
    if not SETTINGS.paths.raw_m5_dir.joinpath(SETTINGS.m5.sales_file).exists():
        pytest.skip("raw sales CSV not present")
    # SUM(COLUMNS(...)) returns one total per d_ column; we add those up in Python.
    # A separate in-memory connection reads the raw CSV independently of the warehouse.
    with duckdb.connect(":memory:") as raw:
        per_day = raw.execute(
            f"SELECT SUM(COLUMNS('^d_[0-9]+$')) FROM read_csv('{sales_csv}', header = true)"
        ).fetchone()
    assert scalar(con, "SELECT SUM(units_sold) FROM fact_sales") == sum(per_day)
