"""Unit tests for the M5 loader, run against a tiny synthetic ("fixture") dataset.

These tests don't need the real Kaggle data: they build 3 miniature CSVs with the same
columns as M5, run the real loader code on them, and check the output. That makes them
fast (< 1 second) and runnable anywhere, including CI, where M5 can't be stored.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from supplier_copilot.db.duckdb_client import read_schema_sql
from supplier_copilot.ingestion.m5_loader import M5Files, load_m5

# ---- Synthetic mini-M5: 2 items x 2 stores x 3 days, 4 calendar days (calendar is
# ---- longer than sales, exactly like the real data: d_1942+ exist only in calendar).

CALENDAR_CSV = """date,wm_yr_wk,weekday,wday,month,year,d,event_name_1,event_type_1,event_name_2,event_type_2,snap_CA,snap_TX,snap_WI
2011-01-29,11101,Saturday,1,1,2011,d_1,,,,,0,0,0
2011-01-30,11101,Sunday,2,1,2011,d_2,SuperBowl,Sporting,,,1,0,1
2011-01-31,11101,Monday,3,1,2011,d_3,,,,,0,1,0
2011-02-01,11101,Tuesday,4,2,2011,d_4,,,,,0,0,0
"""

SALES_CSV = """id,item_id,dept_id,cat_id,store_id,state_id,d_1,d_2,d_3
FOODS_1_001_CA_1_evaluation,FOODS_1_001,FOODS_1,FOODS,CA_1,CA,3,0,5
FOODS_1_001_TX_1_evaluation,FOODS_1_001,FOODS_1,FOODS,TX_1,TX,1,2,0
HOBBIES_1_001_CA_1_evaluation,HOBBIES_1_001,HOBBIES_1,HOBBIES,CA_1,CA,0,0,0
HOBBIES_1_001_TX_1_evaluation,HOBBIES_1_001,HOBBIES_1,HOBBIES,TX_1,TX,4,0,1
"""

# HOBBIES_1_001 has no CA_1 price: models an item not yet stocked in that store.
PRICES_CSV = """store_id,item_id,wm_yr_wk,sell_price
CA_1,FOODS_1_001,11101,2.50
TX_1,FOODS_1_001,11101,2.25
TX_1,HOBBIES_1_001,11101,9.99
"""


@pytest.fixture
def loaded_db(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """Write the mini CSVs to a temp folder, build an in-memory DB, run the loader.

    tmp_path is a pytest built-in: a fresh, empty folder per test, deleted afterwards.
    """
    (tmp_path / "calendar.csv").write_text(CALENDAR_CSV)
    (tmp_path / "sales.csv").write_text(SALES_CSV)
    (tmp_path / "prices.csv").write_text(PRICES_CSV)

    con = duckdb.connect(":memory:")  # in-memory database: nothing written to disk
    con.execute(read_schema_sql())
    load_m5(con, M5Files.from_dir(tmp_path, "sales.csv", "calendar.csv", "prices.csv"))
    yield con
    con.close()


def test_row_counts(loaded_db):
    def q(table: str) -> int:
        return loaded_db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    assert q("dim_date") == 4
    assert q("dim_item") == 2
    assert q("dim_store") == 2
    assert q("fact_sales") == 2 * 2 * 3  # items x stores x sales days
    assert q("fact_prices") == 3


def test_unpivot_maps_day_codes_to_dates(loaded_db):
    """The value under column d_3 for FOODS_1_001 @ CA_1 must land on 2011-01-31."""
    units = loaded_db.execute("""
        SELECT units_sold FROM fact_sales
        WHERE item_id = 'FOODS_1_001' AND store_id = 'CA_1' AND date = DATE '2011-01-31'
    """).fetchone()[0]
    assert units == 5


def test_total_units_reconcile_with_source(loaded_db):
    """Reconciliation: no units are lost or duplicated by the transform."""
    total = loaded_db.execute("SELECT SUM(units_sold) FROM fact_sales").fetchone()[0]
    assert total == (3 + 0 + 5) + (1 + 2 + 0) + (0 + 0 + 0) + (4 + 0 + 1)


def test_calendar_types_and_flags(loaded_db):
    row = loaded_db.execute(
        "SELECT date, event_name_1, snap_ca, snap_tx, snap_wi FROM dim_date WHERE d = 'd_2'"
    ).fetchone()
    assert row == (date(2011, 1, 30), "SuperBowl", True, False, True)


def test_dimensions_are_deduplicated(loaded_db):
    cats = loaded_db.execute("SELECT item_id, cat_id FROM dim_item ORDER BY item_id").fetchall()
    assert cats == [("FOODS_1_001", "FOODS"), ("HOBBIES_1_001", "HOBBIES")]


def test_view_computes_revenue_and_keeps_unpriced_rows(loaded_db):
    # Priced row: 3 units x $2.50 = $7.50
    rev = loaded_db.execute("""
        SELECT revenue FROM v_daily_sales
        WHERE item_id = 'FOODS_1_001' AND store_id = 'CA_1' AND date = DATE '2011-01-29'
    """).fetchone()[0]
    assert float(rev) == pytest.approx(7.50)
    # Unpriced item-store still appears (LEFT JOIN) with NULL price
    n_unpriced = loaded_db.execute("""
        SELECT COUNT(*) FROM v_daily_sales
        WHERE item_id = 'HOBBIES_1_001' AND store_id = 'CA_1' AND sell_price IS NULL
    """).fetchone()[0]
    assert n_unpriced == 3


def test_staging_table_is_dropped(loaded_db):
    tables = {r[0] for r in loaded_db.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    assert "stg_sales_wide" not in tables


def test_loader_is_idempotent(loaded_db, tmp_path):
    """Running the load a second time must not duplicate rows."""
    load_m5(loaded_db, M5Files.from_dir(tmp_path, "sales.csv", "calendar.csv", "prices.csv"))
    assert loaded_db.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0] == 12


def test_missing_file_fails_fast(tmp_path):
    with pytest.raises(FileNotFoundError, match="Missing M5 file"):
        M5Files.from_dir(tmp_path, "a.csv", "b.csv", "c.csv").check_exist()
