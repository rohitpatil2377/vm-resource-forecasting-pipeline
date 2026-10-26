# src/minio_reader.py

from minio import Minio
import pandas as pd
import pyarrow.parquet as pq
import io
from datetime import timezone

from src.logger import get_logger
from src.utils import load_yaml

logger = get_logger("minio_reader")

# ============================================================
# LOAD CONFIG
# ============================================================
def load_minio_config() -> dict:
    cfg = load_yaml("config/minio.yaml")["minio"]

    return {
        "endpoint": cfg["endpoint"],
        "access_key": cfg["access_key"],
        "secret_key": cfg["secret_key"],
        "secure": cfg.get("secure", True),
        "bucket": cfg["bucket"],
        "prefix": cfg["prefix"]  # influxdb/monitoring-data
    }


# ============================================================
# CLIENT
# ============================================================
def get_minio_client(cfg: dict) -> Minio:
    return Minio(
        endpoint=cfg["endpoint"],
        access_key=cfg["access_key"],
        secret_key=cfg["secret_key"],
        secure=cfg["secure"]
    )


# ============================================================
# INTERNAL PARQUET READER
# ============================================================
def _read_single_parquet(
    client: Minio,
    bucket: str,
    object_name: str
) -> pd.DataFrame:
    logger.info(f"📥 Reading object: {object_name}")

    response = client.get_object(bucket, object_name)
    try:
        data = response.read()
        table = pq.read_table(io.BytesIO(data))
        df = table.to_pandas()
        return df
    finally:
        response.close()
        response.release_conn()


# ============================================================
# GENERIC FORECAST READER
# ============================================================
def _read_forecast_file(
    client: Minio,
    bucket: str,
    prefix: str,
    run_date: str,
    forecast_type: str
) -> pd.DataFrame:
    """
    forecast_type: cpu | memory
    """

    object_name = (
        f"{prefix}/forecasted-data/"
        f"{forecast_type}_forecast_{run_date}.parquet"
    )

    logger.info(
        f"📥 Reading {forecast_type.upper()} forecast from MinIO | "
        f"path={object_name}"
    )

    try:
        df = _read_single_parquet(
            client=client,
            bucket=bucket,
            object_name=object_name
        )
    except Exception as e:
        logger.warning(
            f"❌ Forecast file not found: {object_name}"
        )
        return pd.DataFrame()

    # Ensure UTC timestamps
    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
        errors="coerce"
    )

    logger.info(
        f"Loaded {forecast_type} forecast | rows={len(df)} | "
        f"VMs={df['vm_uuid'].nunique()}"
    )

    return df


# ============================================================
# PUBLIC API
# ============================================================
def read_cpu_forecast(
    client: Minio,
    bucket: str,
    prefix: str,
    run_date: str
) -> pd.DataFrame:
    return _read_forecast_file(
        client=client,
        bucket=bucket,
        prefix=prefix,
        run_date=run_date,
        forecast_type="cpu"
    )


def read_memory_forecast(
    client: Minio,
    bucket: str,
    prefix: str,
    run_date: str
) -> pd.DataFrame:
    return _read_forecast_file(
        client=client,
        bucket=bucket,
        prefix=prefix,
        run_date=run_date,
        forecast_type="memory"
    )
