"""One place to configure logging for the whole project.

Why logging instead of print():
  - every line gets a timestamp, severity level, and the module that wrote it
  - verbosity is controlled by LOG_LEVEL without touching code
  - in production, the same logs can be shipped to a monitoring system
"""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger once, at program start (called by entry-point scripts)."""
    logging.basicConfig(
        level=level.upper(),
        format=LOG_FORMAT,
        datefmt="%H:%M:%S",
        force=True,  # replace any handlers set earlier, so calling this twice is harmless
    )
