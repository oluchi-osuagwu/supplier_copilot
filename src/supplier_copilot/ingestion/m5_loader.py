"""Load the M5 (Walmart) CSVs into the DuckDB star schema.

Pipeline (an ELT pattern: Extract -> Load -> Transform, where the transform runs as
SQL *inside* the database instead of in pandas):

    calendar.csv               -> dim_date
    sales_train_evaluation.csv -> stg_sales_wide (temp) -> dim_item, dim_store
                                                        -> UNPIVOT -> fact_sales
    sell_prices.csv            -> fact_prices

Why DuckDB SQL rather than pandas: the unpivot produces ~59 million rows. pandas would
hold everything in RAM as Python objects; DuckDB is a columnar, vectorized engine that
processes data in compressed batches, uses all CPU cores, and spills to disk if needed.

Every function takes the connection and file paths as arguments (dependency injection),
so the unit tests can run the exact same code on tiny synthetic CSVs.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class M5Files:
    """The three raw files the loader needs. frozen=True makes it immutable."""

    sales: Path
    calendar: Path
    prices: Path

    @classmethod
    def from_dir(cls, raw_dir: Path, sales: str, calendar: str, prices: str) -> M5Files:
        return cls(sales=raw_dir / sales, calendar=raw_dir / calendar, prices=raw_dir / prices)

    def check_exist(self) -> None:
        """Fail fast with a helpful message if a file is missing."""
        missing = [str(p) for p in (self.sales, self.calendar, self.prices) if not p.exists()]
        if missing:
            raise FileNotFoundError(
                "Missing M5 file(s): " + ", ".join(missing)
                + ". Download from kaggle.com/c/m5-forecasting-accuracy (accept the rules) "
                "and place the CSVs in data/raw/m5/."
            )


def _sql_path(path: Path) -> str:
    """Format a file path as a SQL string literal (forward slashes, escaped quotes)."""
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def _count(con: duckdb.DuckDBPyConnection, table: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def load_calendar(con: duckdb.DuckDBPyConnection, calendar_csv: Path) -> int:
    """calendar.csv -> dim_date. Casts types explicitly and turns 0/1 SNAP flags into booleans."""
    con.execute("DELETE FROM dim_date")  # makes the function safe to re-run
    con.execute(f"""
        INSERT INTO dim_date
        SELECT
            CAST(date AS DATE),
            d,
            CAST(wm_yr_wk AS INTEGER),
            weekday,
            CAST(wday AS TINYINT),
            CAST(month AS TINYINT),
            CAST(year AS SMALLINT),
            event_name_1, event_type_1, event_name_2, event_type_2,
            snap_CA = 1, snap_TX = 1, snap_WI = 1   -- 0/1 integer flags -> TRUE/FALSE
        FROM read_csv({_sql_path(calendar_csv)}, header = true)
    """)
    return _count(con, "dim_date")


def stage_sales_wide(con: duckdb.DuckDBPyConnection, sales_csv: Path) -> int:
    """Read the wide sales CSV once into a TEMP table (a staging table).

    TEMP tables live only for this connection and are never saved to the database file.
    Staging means we parse the 120 MB CSV once, then derive several tables from it.
    """
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE stg_sales_wide AS
        SELECT * FROM read_csv({_sql_path(sales_csv)}, header = true)
    """)
    return _count(con, "stg_sales_wide")


def load_dimensions(con: duckdb.DuckDBPyConnection) -> tuple[int, int]:
    """Derive dim_item and dim_store from the staged sales table.

    The wide file repeats each item's dept/category on every store row; SELECT DISTINCT
    collapses those repeats into one row per item (and one per store). This is
    normalization: each fact (an item's category) is stored exactly once.
    """
    con.execute("DELETE FROM dim_item")
    con.execute("""
        INSERT INTO dim_item
        SELECT DISTINCT item_id, dept_id, cat_id FROM stg_sales_wide ORDER BY item_id
    """)
    con.execute("DELETE FROM dim_store")
    con.execute("""
        INSERT INTO dim_store
        SELECT DISTINCT store_id, state_id FROM stg_sales_wide ORDER BY store_id
    """)
    return _count(con, "dim_item"), _count(con, "dim_store")


def load_sales_fact(con: duckdb.DuckDBPyConnection) -> int:
    """Wide -> long: UNPIVOT the d_1..d_1941 columns into one row per (item, store, day).

    Before (wide):  item | store | d_1 | d_2 | ... | d_1941      (30,490 rows x 1,947 cols)
    After  (long):  item | store | d   | units_sold              (~59 million rows x 4 cols)

    Then the M5 day code (d_1) is swapped for a real DATE by joining to dim_date.
    ORDER BY date physically clusters rows by date. DuckDB keeps min/max statistics per
    block of rows ("zone maps"), so a query for "Q3 2015" can skip blocks outside that
    range entirely, and nearly every supplier question has a date filter.
    """
    con.execute("DELETE FROM fact_sales")
    con.execute("""
        INSERT INTO fact_sales
        SELECT u.item_id, u.store_id, cal.date, CAST(u.units_sold AS INTEGER)
        FROM (
            UNPIVOT stg_sales_wide
            ON COLUMNS('^d_[0-9]+$')        -- regex: every column named d_<number>
            INTO NAME d VALUE units_sold
        ) AS u
        JOIN dim_date AS cal ON cal.d = u.d
        ORDER BY cal.date, u.store_id, u.item_id
    """)
    return _count(con, "fact_sales")


def load_prices(con: duckdb.DuckDBPyConnection, prices_csv: Path) -> int:
    """sell_prices.csv -> fact_prices (already long format: one row per item/store/week)."""
    con.execute("DELETE FROM fact_prices")
    con.execute(f"""
        INSERT INTO fact_prices
        SELECT item_id, store_id, CAST(wm_yr_wk AS INTEGER), CAST(sell_price AS DECIMAL(10,2))
        FROM read_csv({_sql_path(prices_csv)}, header = true)
        ORDER BY wm_yr_wk, store_id, item_id
    """)
    return _count(con, "fact_prices")


def load_m5(con: duckdb.DuckDBPyConnection, m5_files: M5Files) -> dict[str, int]:
    """Run the full M5 load in dependency order and return row counts per table.

    Order matters: dim_date must exist before fact_sales, because the unpivot joins
    to it to convert day codes into dates.
    """
    m5_files.check_exist()
    counts: dict[str, int] = {}

    steps = [
        ("dim_date", lambda: load_calendar(con, m5_files.calendar)),
        ("stg_sales_wide", lambda: stage_sales_wide(con, m5_files.sales)),
        ("dim_item+dim_store", lambda: load_dimensions(con)),
        ("fact_sales", lambda: load_sales_fact(con)),
        ("fact_prices", lambda: load_prices(con, m5_files.prices)),
    ]
    for name, step in steps:
        start = time.perf_counter()
        result = step()
        elapsed = time.perf_counter() - start
        if isinstance(result, tuple):  # load_dimensions returns two counts
            counts["dim_item"], counts["dim_store"] = result
        else:
            counts[name] = result
        logger.info("Loaded %-20s -> %s rows in %.1fs", name, result, elapsed)

    con.execute("DROP TABLE IF EXISTS stg_sales_wide")  # staging data is no longer needed
    counts.pop("stg_sales_wide", None)
    return counts
