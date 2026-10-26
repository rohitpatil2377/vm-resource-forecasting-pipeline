# src/minio_reader.py

import io
import gc
import pandas as pd
import pyarrow.parquet as pq
from datetime import datetime, timedelta
from typing import List

from minio import Minio

from src.utils import load_yaml
from src.logger import get_logger

logger = get_logger("minio_reader")

# ============================================================
# LOAD MINIO CONFIG
# ============================================================
def load_minio_config() -> dict:
    """
    Loads MinIO configuration from config/minio.yaml
    """
    return load_yaml("config/minio.yaml")["minio"]


# ============================================================
# CREATE MINIO CLIENT
# ============================================================
def get_minio_client(cfg: dict) -> Minio:
    """
    Creates and returns MinIO client
    """
    return Minio(
        endpoint=cfg["endpoint"],
        access_key=cfg["access_key"],
        secret_key=cfg["secret_key"],
        secure=cfg.get("secure", True),
    )


# ============================================================
# COMMON MINIO CONTEXT (USED EVERYWHERE)
# ============================================================
def get_minio_context():
    """
    Returns:
      - MinIO client
      - MinIO config dict
    """
    cfg = load_minio_config()
    client = get_minio_client(cfg)
    return client, cfg


# ============================================================
# READ PARQUET FILES FROM MINIO
# ============================================================
def read_parquet_from_minio(
    client: Minio,
    bucket: str,
    prefix: str,
    start: datetime,
    end: datetime,
    vm_list: List[str]
) -> pd.DataFrame:
    """
    Reads parquet files from MinIO and filters by:
      - time window
      - VM UUID list
    """

    dfs = []

    for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
        if not obj.object_name.endswith(".parquet"):
            continue

        response = client.get_object(bucket, obj.object_name)
        table = pq.read_table(io.BytesIO(response.read()))
        response.close()
        response.release_conn()

        dfs.append(table.to_pandas())

    if not dfs:
        logger.warning("No parquet files found in MinIO")
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)

    # ---------- Standardize ----------
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    if vm_list:
        df = df[df["vm_uuid"].isin(vm_list)]

    df = df[
        (df["timestamp"] >= start) &
        (df["timestamp"] < end)
    ]

    return (
        df.sort_values(["vm_uuid", "timestamp"])
          .reset_index(drop=True)
    )


# ============================================================
# WRITE DATAFRAME TO MINIO (PARQUET)
# ============================================================
def write_df_to_minio(
    client: Minio,
    bucket: str,
    object_name: str,
    df: pd.DataFrame
):
    """
    Writes a DataFrame as parquet into MinIO
    """

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)

    client.put_object(
        bucket_name=bucket,
        object_name=object_name,
        data=buffer,
        length=buffer.getbuffer().nbytes,
        content_type="application/octet-stream"
    )

    logger.info(f"📦 Written to MinIO: {object_name}")


# ============================================================
# FETCH RAW DATA ENTRY (USED BY PIPELINE)
# ============================================================
def fetch_and_store_raw_data(run_date: str):
    """
    Reads 1-minute processed data from MinIO
    """

    from datetime import timezone

    client, cfg = get_minio_context()
    pipeline_cfg = load_yaml("config/pipeline.yaml")["pipeline"]

    history_months = pipeline_cfg["history_months"]

    # ✅ MAKE DATETIMES UTC-AWARE
    run_dt = datetime.strptime(run_date, "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )
    start_dt = run_dt - timedelta(days=history_months * 30)

    logger.info(
        f"Reading MinIO data | start={start_dt} end={run_dt}"
    )

    df = read_parquet_from_minio(
        client=client,
        bucket=cfg["bucket"],
        prefix=f"{cfg['prefix']}/processed-data",
        start=start_dt,
        end=run_dt,
        vm_list=[]  # empty = all VMs
    )

    status_df = pd.DataFrame({
        "vm_uuid": df["vm_uuid"].unique(),
        "eligible": True,
        "comment": "Loaded from MinIO"
    })

    gc.collect()
    return df, status_df

