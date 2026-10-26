# src/preprocess.py

import pandas as pd
import numpy as np
from typing import Tuple, Dict

from src.logger import get_logger
logger = get_logger("preprocess")

# ============================================================
# CONFIG (LOCKED RULES)
# ============================================================
EXPECTED_FREQ = pd.Timedelta(minutes=1)
MAX_ALLOWED_GAP = pd.Timedelta(days=1)   # > 1 day → drop VM


# ============================================================
# Validate raw schema
# ============================================================
def validate_raw_schema(df: pd.DataFrame):
    required_cols = {"timestamp", "vm_uuid", "cpu_used", "memory_used"}
    missing = required_cols - set(df.columns)

    if missing:
        logger.error(f"Missing required columns: {missing}")
        raise ValueError(f"Missing required columns: {missing}")

    if df.empty:
        logger.error("Input DataFrame is empty")
        raise ValueError("Input DataFrame is empty")


# ============================================================
# Compute time gaps per VM
# ============================================================
def compute_time_gaps(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Computing time gaps per VM")

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.sort_values(["vm_uuid", "timestamp"]).reset_index(drop=True)

    df["time_gap"] = (
        df.groupby("vm_uuid")["timestamp"]
          .diff()
          .fillna(pd.Timedelta(seconds=0))
    )

    logger.info("Time gap computation completed")
    return df


# ============================================================
# Summarize missing data (before / after)
# ============================================================
def summarize_missing(df: pd.DataFrame) -> pd.DataFrame:
    summary = []

    for vm, g in df.groupby("vm_uuid"):
        total = len(g)
        missing_cpu = g["cpu_used"].isna().sum()
        missing_mem = g["memory_used"].isna().sum()

        summary.append({
            "vm_uuid": vm,
            "rows": total,
            "cpu_missing_pct": round(missing_cpu / total * 100, 2),
            "memory_missing_pct": round(missing_mem / total * 100, 2),
            "max_gap_minutes": round(
                g["time_gap"].max().total_seconds() / 60, 2
            )
        })

    return pd.DataFrame(summary)


# ============================================================
# Rule-based gap filling (PER VM)
# ============================================================
def fill_gaps_rule_based(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Starting rule-based gap filling")

    filled_dfs = []

    for vm, g in df.groupby("vm_uuid"):
        g = g.sort_values("timestamp").reset_index(drop=True)

        # Build complete 1-minute timeline
        full_time = pd.date_range(
            start=g["timestamp"].min(),
            end=g["timestamp"].max(),
            freq="1min",
            tz="UTC"
        )

        g = (
            g.set_index("timestamp")
             .reindex(full_time)
             .rename_axis("timestamp")
             .reset_index()
        )

        g["vm_uuid"] = vm
        g["time_gap"] = g["timestamp"].diff()

        # -------- RULES --------

        # 1–5 min → ffill + bfill
        g[["cpu_used", "memory_used"]] = (
            g[["cpu_used", "memory_used"]]
            .ffill(limit=5)
            .bfill(limit=5)
        )

        # 6–30 min → rolling 30-min mean
        g[["cpu_used", "memory_used"]] = (
            g[["cpu_used", "memory_used"]]
            .fillna(
                g[["cpu_used", "memory_used"]]
                .rolling(window=30, min_periods=1)
                .mean()
            )
        )

        # 31–120 min → rolling hourly mean
        g[["cpu_used", "memory_used"]] = (
            g[["cpu_used", "memory_used"]]
            .fillna(
                g[["cpu_used", "memory_used"]]
                .rolling(window=60, min_periods=1)
                .mean()
            )
        )

        # 121–1440 min → diurnal mean
        g["hour"] = g["timestamp"].dt.hour
        for col in ["cpu_used", "memory_used"]:
            hod_mean = g.groupby("hour")[col].transform("mean")
            g[col] = g[col].fillna(hod_mean)

        g = g.drop(columns=["hour"])
        filled_dfs.append(g)

    logger.info("Gap filling completed")
    return pd.concat(filled_dfs, ignore_index=True)


# ============================================================
# Drop VMs with gaps > 1 day
# ============================================================
def drop_bad_vms(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    logger.info("Checking for VMs with excessive gaps")

    vm_stats = []

    for vm, g in df.groupby("vm_uuid"):
        max_gap = g["time_gap"].max()

        vm_stats.append({
            "vm_uuid": vm,
            "max_gap_minutes": max_gap.total_seconds() / 60,
            "dropped": max_gap > MAX_ALLOWED_GAP
        })

    stats_df = pd.DataFrame(vm_stats)

    good_vms = stats_df.loc[~stats_df["dropped"], "vm_uuid"]
    df_clean = df[df["vm_uuid"].isin(good_vms)].reset_index(drop=True)

    logger.info(
        f"VMs dropped: {stats_df['dropped'].sum()} / {len(stats_df)}"
    )

    return df_clean, stats_df


# ============================================================
# MAIN PREPROCESS ENTRY
# ============================================================
def preprocess_raw_data(
    df_raw: pd.DataFrame
) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """
    Returns:
      - df_clean_1min
      - summary dict:
          * before_fill
          * after_fill
          * dropped_vms
    """

    logger.info("🧹 Starting preprocessing pipeline")
    logger.info(f"Input rows: {len(df_raw)}")
    logger.info(f"Input VMs: {df_raw['vm_uuid'].nunique()}")

    validate_raw_schema(df_raw)

    # -------- Before fill --------
    df_gap = compute_time_gaps(df_raw)
    summary_before = summarize_missing(df_gap)

    logger.info("Missing summary BEFORE fill:\n" +
                summary_before.to_string(index=False))

    # -------- Gap filling --------
    df_filled = fill_gaps_rule_based(df_gap)

    # -------- Drop bad VMs --------
    df_clean, drop_stats = drop_bad_vms(df_filled)

    logger.info("Dropped VM summary:\n" +
                drop_stats.to_string(index=False))

    # -------- After fill --------
    summary_after = summarize_missing(df_clean)

    logger.info("Missing summary AFTER fill:\n" +
                summary_after.to_string(index=False))

    logger.info(
        f"Preprocessing completed | Output rows: {len(df_clean)} | "
        f"VMs: {df_clean['vm_uuid'].nunique()}"
    )

    return df_clean, {
        "before_fill": summary_before,
        "after_fill": summary_after,
        "dropped_vms": drop_stats
    }
