from datetime import datetime, timedelta, timezone
from influxdb_client import InfluxDBClient

from src.logger import get_logger
from src.influx_writer import load_influx_config

logger = get_logger("influx_cleanup")


# ============================================================
# DELETE OLD FORECAST DATA (ROLLING RETENTION)
# ============================================================
def delete_old_forecasts(retention_days: int = 7):
    """
    Keeps only last `retention_days` of past forecast data.
    Deletes exactly one old day per daily run.
    """

    cfg = load_influx_config()

    client = InfluxDBClient(
        url=cfg["url"],
        token=cfg["token"],
        org=cfg["org"]
    )

    delete_api = client.delete_api()

    # Delete everything BEFORE (today - retention_days)
    stop = (
        datetime.now(timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        - timedelta(days=retention_days)
    )

    predicate = 'data_type="forecast"'   # 🔐 SAFE DELETE

    logger.warning(
        f"🧹 Deleting forecast data older than {retention_days} days | "
        f"before={stop.isoformat()}"
    )

    delete_api.delete(
        start=datetime(1970, 1, 1, tzinfo=timezone.utc),
        stop=stop,
        predicate=predicate,
        bucket=cfg["bucket"],
        org=cfg["org"]
    )

    logger.warning("✅ Forecast retention cleanup completed")

    client.close()


# ============================================================
# ENTRYPOINT
# ============================================================
if __name__ == "__main__":
    delete_old_forecasts(retention_days=7)
