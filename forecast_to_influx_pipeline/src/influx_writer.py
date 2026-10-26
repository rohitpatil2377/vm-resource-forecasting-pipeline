# src/influx_writer.py
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import pandas as pd
from src.logger import get_logger
from src.utils import load_yaml
logger = get_logger("influx_writer")

# ============================================================
# LOAD CONFIG
# ============================================================
def load_influx_config() -> dict:
    cfg = load_yaml("config/influxdb.yaml")["influxdb"]
    token = cfg.get("token")
    if not token:
        token = __import__("os").getenv(cfg["token_env"])
    if not token:
        raise RuntimeError("InfluxDB token not provided")
    return {
        "url": cfg["url"],
        "org": cfg["org"],
        "bucket": cfg["bucket"],
        "token": token,
    }

# ============================================================
# WRITER FACTORY
# ============================================================
def get_influx_writer():
    cfg = load_influx_config()
    client = InfluxDBClient(
        url=cfg["url"],
        token=cfg["token"],
        org=cfg["org"]
    )
    # 🔥 SYNCHRONOUS write = NO background thread issues
    write_api = client.write_api(write_options=SYNCHRONOUS)
    logger.info("✅ InfluxDB writer initialized")
    return write_api, client, cfg

# ============================================================
# WRITE FORECAST DATAFRAME (UPDATED)
# ============================================================
def write_forecast_df(
    write_api,
    cfg: dict,
    measurement: str,
    df: pd.DataFrame,
    forecast_field: str,
    convert_to_ist: bool = True
):
    """
    Writes forecast DataFrame into EXISTING measurement.
    measurement:
      - cpu_usage
      - memory_usage
    forecast_field:
      - cpu_used_forecast
      - memory_used_forecast
    convert_to_ist:
      - If True, converts UTC timestamps to IST (UTC + 5:30) before writing
      - Example: 2026-02-02 00:01:00 IST → 2026-02-01 18:31:00 UTC
      - InfluxDB stores in UTC, but this allows querying with IST business hours
    Tags:
      - vm_uuid
      - data_type=forecast
    """
    logger.info(
        f"📤 Writing forecast → measurement={measurement} | rows={len(df)}"
    )
    # Convert timezone if needed
    df_write = df.copy()
    if convert_to_ist:
        logger.info("Converting forecast timestamps to IST timezone for InfluxDB")
        logger.info("Note: InfluxDB stores in UTC, but timestamps will represent IST times")
        # Ensure UTC-aware
        if df_write["timestamp"].dt.tz is None:
            df_write["timestamp"] = df_write["timestamp"].dt.tz_localize("UTC")
        elif str(df_write["timestamp"].dt.tz) != "UTC":
            df_write["timestamp"] = df_write["timestamp"].dt.tz_convert("UTC")
        logger.info(f"Original UTC timestamps: {df_write['timestamp'].min()} to {df_write['timestamp'].max()}")
        # Subtract 5:30 to convert UTC to IST equivalent
        # Example: 2026-02-02 00:01:00 UTC → 2026-02-01 18:31:00 UTC
        # This 18:31 UTC represents 00:01 IST (next day)
        df_write["timestamp"] = df_write["timestamp"] - pd.Timedelta(hours=5, minutes=30)
        # Keep as UTC-aware for InfluxDB
        logger.info(f"✓ IST-adjusted timestamps (stored as UTC): {df_write['timestamp'].min()} to {df_write['timestamp'].max()}")
        logger.info("  When queried, these UTC times represent IST business hours")
    points = []
    for row in df_write.itertuples(index=False):
        p = (
            Point(measurement)
            .tag("vm_uuid", row.vm_uuid)          # ✅ existing tag
            .tag("data_type", "forecast")         # 🔥 NEW TAG (for retention delete)
            .field(
                forecast_field,
                float(getattr(row, forecast_field))
            )                                     # ✅ only forecast field
            .time(row.timestamp, WritePrecision.NS)
        )
        points.append(p)
    write_api.write(
        bucket=cfg["bucket"],
        org=cfg["org"],
        record=points
    )
    logger.info(
        f"✅ Successfully wrote {len(points)} forecast points → {measurement}"
    )
 
 