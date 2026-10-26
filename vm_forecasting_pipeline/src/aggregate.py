import pandas as pd
from typing import Dict
from src.logger import get_logger

logger = get_logger("aggregate")

TARGET_FREQ = "15min"

DEFAULT_AGG_MAP = {
    "cpu_used": "mean",
    "memory_used": "mean"
}

def aggregate_to_15min(df_1min: pd.DataFrame) -> pd.DataFrame:
    df = df_1min.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    dfs = []
    for vm, g in df.groupby("vm_uuid"):
        g_agg = (
            g.set_index("timestamp")
             .resample(TARGET_FREQ)
             .agg(DEFAULT_AGG_MAP)
             .reset_index()
        )
        g_agg["vm_uuid"] = vm
        dfs.append(g_agg)

    return pd.concat(dfs, ignore_index=True)

def write_agg_to_minio(df_15min: pd.DataFrame, run_date: str):
    from src.minio_reader import get_minio_context, write_df_to_minio

    client, cfg = get_minio_context()
    object_name = f"{cfg['prefix']}/processed-data/agg_15min_{run_date}.parquet"
    write_df_to_minio(client, cfg["bucket"], object_name, df_15min)
