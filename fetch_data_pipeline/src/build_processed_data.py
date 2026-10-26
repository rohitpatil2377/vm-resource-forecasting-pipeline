# src/build_processed_data.py

import io
import pandas as pd
from minio import Minio

from src.minio_utils import read_parquet_from_minio


# ============================================================
# BUILD COMBINED RAW DATASET (NO TRANSFORMATION)
# ============================================================
def build_processed_dataset(
    minio: Minio,
    bucket: str,
    raw_prefix: str,
    output_object: str,
):
    """
    Combine all raw 1-minute parquet files into a single parquet file.

    RULES (STRICT):
    - NO aggregation
    - NO filtering
    - NO VM dropping
    - Raw data remains immutable
    - Processed layer is a pure union of raw layer
    """

    # --------------------------------------------------
    # LIST RAW PARQUET FILES
    # --------------------------------------------------
    objects = minio.list_objects(
        bucket_name=bucket,
        prefix=f"{raw_prefix}/",
        recursive=True
    )

    parquet_files = sorted(
        obj.object_name
        for obj in objects
        if obj.object_name.endswith("data.parquet")
    )

    if not parquet_files:
        print("⚠️ No raw parquet files found — skipping processed dataset build")
        return {
            "rows": 0,
            "vms": 0,
            "days": 0,
        }

    # --------------------------------------------------
    # READ & COMBINE (RAW = SOURCE OF TRUTH)
    # --------------------------------------------------
    dfs = []

    for obj_name in parquet_files:
        df = read_parquet_from_minio(minio, bucket, obj_name)
        if not df.empty:
            dfs.append(df)

    if not dfs:
        print("⚠️ All raw parquet files are empty — nothing to process")
        return {
            "rows": 0,
            "vms": 0,
            "days": 0,
        }

    combined_df = (
        pd.concat(dfs, ignore_index=True)
        .sort_values(["vm_uuid", "timestamp"])
        .reset_index(drop=True)
    )

    # --------------------------------------------------
    # WRITE PROCESSED DATASET (OVERWRITE SAFE)
    # --------------------------------------------------
    buffer = io.BytesIO()
    combined_df.to_parquet(buffer, index=False)
    buffer.seek(0)

    minio.put_object(
        bucket_name=bucket,
        object_name=output_object,
        data=buffer,
        length=buffer.getbuffer().nbytes,
        content_type="application/octet-stream"
    )

    # --------------------------------------------------
    # METADATA (NO TIMEZONE MUTATION)
    # --------------------------------------------------
    return {
        "rows": int(len(combined_df)),
        "vms": int(combined_df["vm_uuid"].nunique()),
        "days": int(combined_df["timestamp"].dt.date.nunique()),
    }
