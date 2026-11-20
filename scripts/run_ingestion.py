"""Entry point: build the DuckDB warehouse from the raw M5 CSVs.

Usage (from the project root, with the virtual environment active):
    python scripts/run_ingestion.py

The whole build runs inside ONE transaction: either every table loads successfully
and is committed together, or an error rolls everything back, leaving the previous
database untouched. This all-or-nothing property is called atomicity (the "A" in ACID).
"""

from __future__ import annotations

import logging
import time

from supplier_copilot.config import get_settings
from supplier_copilot.db.duckdb_client import apply_schema, get_connection
from supplier_copilot.ingestion.m5_loader import M5Files, load_m5
from supplier_copilot.logging_setup import setup_logging

logger = logging.getLogger("run_ingestion")


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    m5_files = M5Files.from_dir(
        settings.paths.raw_m5_dir,
        sales=settings.m5.sales_file,
        calendar=settings.m5.calendar_file,
        prices=settings.m5.prices_file,
    )
    logger.info("Building warehouse at %s", settings.paths.duckdb_path)
    start = time.perf_counter()

    with get_connection() as con:
        con.execute("BEGIN TRANSACTION")
        try:
            apply_schema(con)
            counts = load_m5(con, m5_files)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")  # undo everything from this run
            logger.exception("Ingestion failed; changes rolled back")
            raise
        con.execute("CHECKPOINT")  # flush the write-ahead log into the main database file

    logger.info("Done in %.1fs. Row counts: %s", time.perf_counter() - start, counts)


if __name__ == "__main__":
    main()
