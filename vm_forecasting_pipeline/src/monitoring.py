import io
import gc
import pandas as pd
import pyarrow.parquet as pq
from datetime import datetime, timedelta
from typing import List, Tuple
from minio import Minio

from src.utils import load_yaml
from src.logger import get_logger
from src.fetch_data import load_vm_list  # reuse existing logic

logger = get_logger("minio_reader")


# ============================================================
# CONFIG
# ============================================================
def load_minio_config() -> dict:
    cfg = load_yaml("config/minio.yaml")["minio"]
    return cfg


def get_minio_client(cfg: dict) -> Minio:
    return Minio(
        endpoint=cfg["endpoint"],
        access_key=cfg["access_key"],
        secret_key=cfg["secret_key"],
        secure=cfg.get("secure", True),
    )


def get_minio_context():
    cfg = load_minio_config()
    client = get_minio_client(cfg)
    return client, cfg


# ============================================================
# READ PARQUET FROM MINIO
# ============================================================
def read_parquet_from_minio(
    client: Minio,
    bucket: str,
    prefix: str,
    start: datetime,
    end: datetime,
    vm_list: List[str]
) -> pd.DataFrame:

    objects = client.list_objects(bucket, prefix=prefix, recursive=True)
    dfs = []

    for obj in objects:
        if not obj.object_name.endswith(".parquet"):
            continue

        resp = client.get_object(bucket, obj.object_name)
        table = pq.read_table(io.BytesIO(resp.read()))
        resp.close()
        resp.release_conn()

        dfs.append(table.to_pandas())

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    df = df[
        (df["timestamp"] >= start) &
        (df["timestamp"] < end) &
        (df["vm_uuid"].isin(vm_list))
    ]

    return df.sort_values(["vm_uuid", "timestamp"]).reset_index(drop=True)


# ============================================================
# WRITE DATAFRAME TO MINIO (PARQUET)
# ============================================================
def write_df_to_minio(
    client: Minio,
    bucket: str,
    object_name: str,
    df: pd.DataFrame
):
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)

    client.put_object(
        bucket,
        object_name,
        buffer,
        length=buffer.getbuffer().nbytes,
        content_type="application/octet-stream"
    )

    logger.info(f"📦 Written to MinIO: {object_name}")


# ============================================================
# MAIN FETCH ENTRY
# ============================================================
def fetch_and_store_raw_data(run_date: str):
    client, cfg = get_minio_context()

    pipeline_cfg = load_yaml("config/pipeline.yaml")["pipeline"]
    history_months = pipeline_cfg["history_months"]

    run_dt = datetime.strptime(run_date, "%Y-%m-%d")
    start_dt = run_dt - timedelta(days=history_months * 30)

    vm_list = load_vm_list()

    df = read_parquet_from_minio(
        client=client,
        bucket=cfg["bucket"],
        prefix=f"{cfg['prefix']}/processed-data",
        start=start_dt,
        end=run_dt,
        vm_list=vm_list
    )

    status_df = pd.DataFrame({
        "vm_uuid": vm_list,
        "eligible": True,
        "comment": "Loaded from MinIO"
    })

    gc.collect()
    return df, status_df
