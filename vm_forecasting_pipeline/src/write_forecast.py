# src/write_forecast.py

import pandas as pd
from src.logger import get_logger
from src.minio_reader import get_minio_context, write_df_to_minio

logger = get_logger("write_forecast")

# ============================================================
# Validate forecast schema
# ============================================================
def validate_forecast_schema(df: pd.DataFrame, required_cols: set):
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Forecast missing required columns: {missing}")

    if df.empty:
        raise ValueError("Forecast DataFrame is empty")


# ============================================================
# Common cleanup before write
# ============================================================
def _prepare_forecast_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Ensure timestamp is datetime (UTC)
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)

    # Sort for sanity & downstream consumers
    df = df.sort_values(["vm_uuid", "timestamp"]).reset_index(drop=True)


    print(df)


    return df


# ============================================================
# Write CPU forecast → MinIO
# ============================================================
def write_cpu_forecast(df_cpu: pd.DataFrame) -> str:
    """
    Writes CPU forecast to MinIO as parquet:
      influxdb/monitoring-data/forecasted-data/cpu_forecast_<run_date>.parquet
    """

    required_cols = {
        "vm_uuid",
        "timestamp",
        "cpu_used_forecast",
        "model_name",
        "run_date",
        "horizon_minutes"
    }

    validate_forecast_schema(df_cpu, required_cols)

    df_cpu = _prepare_forecast_df(df_cpu)

    run_date = str(df_cpu["run_date"].iloc[0])

    client, cfg = get_minio_context()

    object_name = (
        f"{cfg['prefix']}/forecasted-data/"
        f"cpu_forecast_{run_date}.parquet"
    )

    write_df_to_minio(
        client=client,
        bucket=cfg["bucket"],
        object_name=object_name,
        df=df_cpu
    )

    logger.info(f"📈 CPU forecast written to MinIO: {object_name}")

    return object_name


# ============================================================
# Write MEMORY forecast → MinIO
# ============================================================
def write_memory_forecast(df_mem: pd.DataFrame) -> str:
    """
    Writes Memory forecast to MinIO as parquet:
      influxdb/monitoring-data/forecasted-data/memory_forecast_<run_date>.parquet
    """

    required_cols = {
        "vm_uuid",
        "timestamp",
        "memory_used_forecast",
        "model_name",
        "run_date",
        "horizon_minutes"
    }

    validate_forecast_schema(df_mem, required_cols)

    df_mem = _prepare_forecast_df(df_mem)

    run_date = str(df_mem["run_date"].iloc[0])

    client, cfg = get_minio_context()

    object_name = (
        f"{cfg['prefix']}/forecasted-data/"
        f"memory_forecast_{run_date}.parquet"
    )

    write_df_to_minio(
        client=client,
        bucket=cfg["bucket"],
        object_name=object_name,
        df=df_mem
    )

    logger.info(f"📈 Memory forecast written to MinIO: {object_name}")

    return object_name
