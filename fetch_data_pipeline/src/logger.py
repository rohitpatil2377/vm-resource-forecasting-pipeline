import logging
import sys
from datetime import datetime, UTC

# ============================================================
# CONFIGURE YOUR TIME FORMAT HERE (ONE LINE)
# ============================================================

TIME_FORMAT = "YYYY_MM_DD"   # 👈 CHANGE HERE

# Available options:
# ISO_UTC
# YYYY_MM_DD
# DD_MM_YYYY
# YYMMDD_COMPACT
# FULL_VERBOSE


# ============================================================
# TIME FORMATTER
# ============================================================

class UTCFormatter(logging.Formatter):
    """
    UTC-aware formatter with configurable, granular timestamp formats.
    """

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=UTC)

        if TIME_FORMAT == "ISO_UTC":
            # 2026-02-02T14:21:30.123456+00:00
            return dt.isoformat()

        elif TIME_FORMAT == "YYYY_MM_DD":
            # 2026-02-02 14:21:30 UTC
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        elif TIME_FORMAT == "DD_MM_YYYY":
            # 02-02-2026 14:21:30 UTC
            return dt.strftime("%d-%m-%Y %H:%M:%S UTC")

        elif TIME_FORMAT == "YYMMDD_COMPACT":
            # 260202 142130 UTC
            return dt.strftime("%y%m%d %H%M%S UTC")

        elif TIME_FORMAT == "FULL_VERBOSE":
            # 2026-02-02 14:21:30.123 UTC
            return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " UTC"

        else:
            # Safe fallback
            return dt.isoformat()


# ============================================================
# LOGGER FACTORY
# ============================================================

def get_logger(name: str) -> logging.Logger:
    """
    Create or return a UTC, granular-time logger.

    Log format:
    <timestamp> | <LEVEL> | <LOGGER NAME> | <MESSAGE>
    """

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers on re-import
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)

    formatter = UTCFormatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logger.propagate = False
    return logger
