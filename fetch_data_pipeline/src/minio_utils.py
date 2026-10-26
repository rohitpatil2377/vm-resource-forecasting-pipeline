# src/minio_utils.py

import io
import json
import pandas as pd
from typing import List, Set, Dict

from minio import Minio
from minio.error import S3Error

from src.utils import load_yaml


# ============================================================
# LOAD MINIO CLIENT
# ============================================================
def get_minio_client():
    """
    Create and validate MinIO client.
    """
    cfg = load_yaml("configs/minio.yaml")["minio"]

    client = Minio(
        endpoint=cfg["endpoint"],
        access_key=cfg["access_key"],
        secret_key=cfg["secret_key"],
        secure=cfg.get("secure", True)
    )

    bucket = cfg["bucket"]

    if not client.bucket_exists(bucket):
        raise RuntimeError(f"MinIO bucket does not exist: {bucket}")

    return client, bucket


# ============================================================
# LIST EXISTING DAY FOLDERS (YYYY-MM-DD)
# ============================================================
def list_minio_days(
    minio: Minio,
    bucket: str,
    prefix: str
) -> List[str]:
    """
    Return sorted list of unique day folders under a prefix.
    Example: ['2025-09-01', '2025-09-02', ...]
    """
    days = set()

    objects = minio.list_objects(
        bucket_name=bucket,
        prefix=f"{prefix}/",
        recursive=True
    )

    for obj in objects:
        relative = obj.object_name.replace(prefix + "/", "")
        parts = relative.split("/")
        if len(parts) >= 2:
            days.add(parts[0])

    return sorted(days)


# ============================================================
# READ PARQUET FROM MINIO
# ============================================================
def read_parquet_from_minio(
    minio: Minio,
    bucket: str,
    object_path: str
) -> pd.DataFrame:
    """
    Read parquet file from MinIO.
    Returns empty DataFrame if object does not exist.
    """
    try:
        response = minio.get_object(bucket, object_path)
        data = response.read()
        response.close()
        response.release_conn()
        return pd.read_parquet(io.BytesIO(data))

    except S3Error as e:
        if e.code == "NoSuchKey":
            return pd.DataFrame()
        raise


# ============================================================
# GET EXISTING VM UUIDs FOR A DAY
# ============================================================
def get_existing_vms_for_day(
    minio: Minio,
    bucket: str,
    day_object_path: str
) -> Set[str]:
    """
    Return set of vm_uuid already present in a day's parquet file.
    """
    try:
        df = read_parquet_from_minio(minio, bucket, day_object_path)
        if df.empty or "vm_uuid" not in df.columns:
            return set()
        return set(df["vm_uuid"].unique())
    except Exception:
        return set()


# ============================================================
# WRITE PARQUET TO MINIO
# ============================================================
def write_parquet_to_minio(
    minio: Minio,
    bucket: str,
    object_path: str,
    df: pd.DataFrame
):
    """
    Write DataFrame as parquet to MinIO.
    Overwrites object if it already exists.
    """
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)

    minio.put_object(
        bucket_name=bucket,
        object_name=object_path,
        data=buffer,
        length=buffer.getbuffer().nbytes,
        content_type="application/octet-stream"
    )


# ============================================================
# DELETE PREFIX (USED BY PIPELINE FOR RETENTION)
# ============================================================
def delete_minio_prefix(
    minio: Minio,
    bucket: str,
    prefix: str
):
    """
    Delete all objects under a prefix.
    Retention logic is handled in run_pipeline.py.
    """
    objects = minio.list_objects(
        bucket_name=bucket,
        prefix=f"{prefix}/",
        recursive=True
    )

    for obj in objects:
        minio.remove_object(bucket, obj.object_name)


# ============================================================
# JSON METADATA HELPERS (OPTIONAL)
# ============================================================
def write_json_to_minio(
    minio: Minio,
    bucket: str,
    object_path: str,
    payload: Dict
):
    """
    Write JSON metadata to MinIO.
    Folder is created implicitly.
    """
    data = json.dumps(payload, indent=2).encode("utf-8")

    minio.put_object(
        bucket_name=bucket,
        object_name=object_path,
        data=io.BytesIO(data),
        length=len(data),
        content_type="application/json"
    )


def read_json_from_minio(
    minio: Minio,
    bucket: str,
    object_path: str
) -> Dict:
    """
    Read JSON metadata from MinIO.
    Returns empty dict if object does not exist.
    """
    try:
        response = minio.get_object(bucket, object_path)
        data = json.loads(response.read())
        response.close()
        response.release_conn()
        return data
    except Exception:
        return {}
