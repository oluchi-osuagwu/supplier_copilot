"""DuckDB connection management and schema creation.

All database access goes through this module, so swapping DuckDB for Postgres
later means changing this layer, not every file that touches the database.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path

import duckdb

from supplier_copilot.config import get_settings

logger = logging.getLogger(__name__)


@contextmanager
def get_connection(
    db_path: Path | str | None = None,
    read_only: bool = False,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open a DuckDB connection and always close it afterwards.

    Used as:  with get_connection() as con: con.sql("SELECT ...")

    The @contextmanager decorator guarantees the `finally` block runs even if the
    code inside the `with` raises an error, so a crash never leaves the file locked.
    read_only=True is what the API/agent will use later: it physically cannot modify data.
    """
    settings = get_settings()
    path = Path(db_path) if db_path is not None else settings.paths.duckdb_path
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)  # create data/processed/ if missing

    con = duckdb.connect(str(path), read_only=read_only)
    try:
        # Resource limits: cap RAM (DuckDB spills to disk past this) and parallelism.
        con.execute(f"SET memory_limit = '{settings.duckdb.memory_limit}'")
        con.execute(f"SET threads = {int(settings.duckdb.threads)}")
        yield con
    finally:
        con.close()


def read_schema_sql() -> str:
    """Load schema.sql from inside the installed package (works regardless of working directory)."""
    return files("supplier_copilot.db").joinpath("schema.sql").read_text(encoding="utf-8")


def apply_schema(con: duckdb.DuckDBPyConnection) -> None:
    """(Re)create all tables and views defined in schema.sql. Idempotent."""
    con.execute(read_schema_sql())
    logger.info("Schema applied (dim_date, dim_store, dim_item, fact_sales, fact_prices, v_daily_sales)")
