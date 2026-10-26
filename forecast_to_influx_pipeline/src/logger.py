# src/logger.py

import logging
import os
from datetime import datetime, timezone

# ============================================================
# LOG DIRECTORY
# ============================================================
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)


# ============================================================
# UTC FORMATTER
# ============================================================
class UTCFormatter(logging.Formatter):
    """
    Ensures all log timestamps are in UTC.
    """

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# ============================================================
# LOGGER FACTORY
# ============================================================
def get_logger(name: str = "forecast_sync") -> logging.Logger:
    """
    Creates and returns a configured logger.

    - Logs to console
    - Logs to logs/forecast_sync_<UTC_DATE>.log
    - Uses UTC timestamps explicitly
    """

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"forecast_sync_{run_date}.log")

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    formatter = UTCFormatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    # -------- File handler --------
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)

    # -------- Console handler --------
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(sh)

    logger.propagate = False
    return logger
