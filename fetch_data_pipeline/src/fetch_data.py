# src/fetch_data.py

import pandas as pd
import warnings
from typing import List, Iterable
from datetime import datetime, timedelta, timezone

from influxdb_client import InfluxDBClient
from influxdb_client.client.warnings import MissingPivotFunction

from src.utils import load_yaml

# ============================================================
# Silence Influx pivot warnings
# ============================================================
warnings.simplefilter("ignore", MissingPivotFunction)

# ============================================================
# CONSTANTS
# ============================================================
AGG_WINDOW = "1m"        # 1-minute MAX aggregation (spike-preserving)
BATCH_SIZE = 50          # Protect InfluxDB from large OR filters

# ============================================================
# CONFIG LOADERS
# ============================================================
def load_influx() -> dict:
    """
    Load InfluxDB configuration.
    """
    return load_yaml("configs/influxdb.yaml")["influxdb"]


def load_vm_list() -> List[str]:
    """
    Load VM UUID snapshot written by vm_uuid_collector.
    """
    cfg = load_yaml("configs/vm_source.yaml")["vm_source"]
    return cfg.get("vm_list", [])


# ============================================================
# INFLUX CLIENT
# ============================================================
def get_query_api(cfg: dict):
    """
    Create InfluxDB Query API.
    """
    client = InfluxDBClient(
        url=cfg["url"],
        token=cfg["token"],
        org=cfg["org"],
        timeout=300_000
    )
    return client.query_api()


# ============================================================
# HELPERS
# ============================================================
def chunk_list(items: List[str], size: int) -> Iterable[List[str]]:
    """
    Yield fixed-size chunks from a list.
    """
    for i in range(0, len(items), size):
        yield items[i:i + size]


# ============================================================
# VM HISTORY CHECK (CHEAP METADATA QUERY)
# ============================================================
def vm_has_min_history(
    query_api,
    bucket: str,
    vm_uuid: str,
    min_days: int
) -> bool:
    """
    Check whether VM has at least `min_days` of historical data.

    Uses only the FIRST datapoint (cheap & fast).
    """

    flux = f"""
    from(bucket: "{bucket}")
      |> range(start: 0)
      |> filter(fn: (r) =>
          r["_measurement"] == "cpu_usage" and
          r["_field"] == "cpu_used" and
          r["vm_uuid"] == "{vm_uuid}"
      )
      |> first()
    """

    df = query_api.query_data_frame(flux)

    # Handle list responses safely
    if isinstance(df, list):
        if not df:
            return False
        df = pd.concat(df, ignore_index=True)

    if df.empty or "_time" not in df.columns:
        return False

    first_ts = df["_time"].min()
    if first_ts.tzinfo is None:
        first_ts = first_ts.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    history_days = (now - first_ts).days

    return history_days >= min_days


# ============================================================
# FETCH ONE DAY OF DATA (SPIKE-PRESERVING)
# ============================================================
def fetch_day_data(
    query_api,
    bucket: str,
    vms: List[str],
    day
) -> pd.DataFrame:
    """
    Fetch 1-minute MAX CPU & memory usage for given VMs on a single day.

    DESIGN GUARANTEES:
    - MAX @ 1m → spike-safe
    - NO smoothing
    - NO destructive filtering
    - Idempotent output
    """

    if not vms:
        return pd.DataFrame()

    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    frames = []

    for batch in chunk_list(vms, BATCH_SIZE):
        vm_filter = " or ".join([f'r["vm_uuid"] == "{v}"' for v in batch])

        flux = f"""
        from(bucket: "{bucket}")
          |> range(start: {start.isoformat()}, stop: {end.isoformat()})
          |> filter(fn: (r) =>
              r["_measurement"] == "cpu_usage" or
              r["_measurement"] == "memory_usage"
          )
          |> filter(fn: (r) =>
              r["_field"] == "cpu_used" or
              r["_field"] == "memory_used"
          )
          |> filter(fn: (r) => {vm_filter})
          |> aggregateWindow(
                every: {AGG_WINDOW},
                fn: max,
                createEmpty: false
          )
          |> pivot(
              rowKey: ["_time", "vm_uuid"],
              columnKey: ["_field"],
              valueColumn: "_value"
          )
          |> keep(columns: ["_time", "vm_uuid", "cpu_used", "memory_used"])
        """

        df = query_api.query_data_frame(flux)

        if isinstance(df, list):
            df = pd.concat(df, ignore_index=True) if df else pd.DataFrame()

        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    # --------------------------------------------------
    # FINAL NORMALIZATION (CRITICAL)
    # Ensures exactly ONE row per (timestamp, vm_uuid)
    # --------------------------------------------------
    return (
        pd.concat(frames, ignore_index=True)
        .rename(columns={"_time": "timestamp"})
        .drop(columns=["result", "table"], errors="ignore")
        .groupby(["timestamp", "vm_uuid"], as_index=False)
        .agg({
            "cpu_used": "max",
            "memory_used": "max"
        })
        .sort_values(["vm_uuid", "timestamp"])
        .reset_index(drop=True)
    )
