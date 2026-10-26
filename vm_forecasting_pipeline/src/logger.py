import logging
import os
import sys
from datetime import datetime, UTC

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
    Logging formatter that:
    - Forces UTC timezone
    - Uses explicit, human-readable format
    - Avoids local timezone ambiguity
    """

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=UTC)
        # Example: 2026-02-02 09:58:05 UTC
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# ============================================================
# LOGGER FACTORY
# ============================================================
def get_logger(name: str = "vm_forecasting") -> logging.Logger:
    """
    Creates or returns a logger with:
    - UTC timestamps
    - Console + file logging
    - One log file per UTC date
    """

    # Log file name based on UTC date
    run_date = datetime.now(UTC).strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"pipeline_{run_date}.log")

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers on re-import
    if logger.handlers:
        return logger

    formatter = UTCFormatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    # --------------------------------------------------
    # FILE HANDLER (persistent logs)
    # --------------------------------------------------
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)

    # --------------------------------------------------
    # STREAM HANDLER (stdout / console)
    # --------------------------------------------------
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    # Do not propagate to root logger
    logger.propagate = False

    return logger

