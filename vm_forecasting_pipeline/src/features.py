# src/features.py

import pandas as pd
import numpy as np
from typing import List
from src.logger import get_logger

logger = get_logger("features")

# ============================================================
# TIME FEATURES (CYCLICALLY CORRECT)
# ============================================================
def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["hour"] = df["timestamp"].dt.hour
    df["minute_bucket"] = df["timestamp"].dt.minute // 15
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    # Daily cycle
    df["sin_hour"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["cos_hour"] = np.cos(2 * np.pi * df["hour"] / 24)

    # Weekly cycle
    df["sin_dow"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["cos_dow"] = np.cos(2 * np.pi * df["day_of_week"] / 7)

    return df


# ============================================================
# DAILY CPU BASELINE (🔥 MOST IMPORTANT FIX)
# ============================================================
def add_cpu_daily_profile(df: pd.DataFrame) -> pd.DataFrame:
    """
    Median CPU usage per VM per (hour, minute_bucket)
    This represents the deterministic daily pattern.
    """

    logger.info("📐 Computing daily CPU baseline profile")

    profile = (
        df.groupby(["vm_uuid", "hour", "minute_bucket"])["cpu_used"]
          .median()
          .rename("cpu_daily_profile")
          .reset_index()
    )

    df = df.merge(
        profile,
        on=["vm_uuid", "hour", "minute_bucket"],
        how="left"
    )

    return df


# ============================================================
# CPU FEATURES (SPIKE + SEASONAL + REGIME AWARE)
# ============================================================
def build_cpu_features(
    df_15min: pd.DataFrame,
    lags: List[int],
    rolling_windows: List[int]
) -> pd.DataFrame:

    logger.info("🧠 Building CPU features")

    # ---- time features ----
    df = add_time_features(df_15min)

    # ---- daily baseline ----
    df = add_cpu_daily_profile(df)

    # ---------------- LAGS ----------------
    for lag in sorted(set(lags + [672])):  # include weekly lag
        df[f"cpu_lag_{lag}"] = (
            df.groupby("vm_uuid")["cpu_used"].shift(lag)
        )

    # ---------------- ROLLING ----------------
    for w in rolling_windows:
        df[f"cpu_roll_mean_{w}"] = (
            df.groupby("vm_uuid")["cpu_used"]
              .rolling(w, min_periods=1)
              .mean()
              .reset_index(level=0, drop=True)
        )

        df[f"cpu_roll_max_{w}"] = (
            df.groupby("vm_uuid")["cpu_used"]
              .rolling(w, min_periods=1)
              .max()
              .reset_index(level=0, drop=True)
        )

    # ---------------- SPIKE / VOLATILITY ----------------
    win = 96  # 24 hours

    df["cpu_std_24h"] = (
        df.groupby("vm_uuid")["cpu_used"]
          .rolling(win, min_periods=1)
          .std()
          .reset_index(level=0, drop=True)
    )

    df["cpu_p95_24h"] = (
        df.groupby("vm_uuid")["cpu_used"]
          .rolling(win, min_periods=1)
          .quantile(0.95)
          .reset_index(level=0, drop=True)
    )

    df["cpu_active_ratio_24h"] = (
        df.groupby("vm_uuid")["cpu_used"]
          .rolling(win, min_periods=1)
          .apply(lambda x: (x > 0.1).mean(), raw=True)
          .reset_index(level=0, drop=True)
    )

    df["cpu_is_spike"] = (
        df["cpu_used"]
        > df.groupby("vm_uuid")["cpu_used"].transform("quantile", 0.95)
    ).astype(int)

    # ---------------- CLEAN ----------------
    lag_cols = [c for c in df.columns if c.startswith("cpu_lag_")]
    df = df.dropna(subset=lag_cols)

    return df.sort_values(["vm_uuid", "timestamp"]).reset_index(drop=True)


# ============================================================
# MEMORY FEATURES (STABLE – NO CHANGE NEEDED)
# ============================================================
def build_memory_features(
    df_15min: pd.DataFrame,
    lags: List[int],
    rolling_windows: List[int]
) -> pd.DataFrame:

    logger.info("🧠 Building MEMORY features")

    df = add_time_features(df_15min)

    for lag in sorted(set(lags + [672])):
        df[f"memory_lag_{lag}"] = (
            df.groupby("vm_uuid")["memory_used"].shift(lag)
        )

    for w in rolling_windows:
        df[f"memory_roll_mean_{w}"] = (
            df.groupby("vm_uuid")["memory_used"]
              .rolling(w, min_periods=1)
              .mean()
              .reset_index(level=0, drop=True)
        )

        df[f"memory_roll_max_{w}"] = (
            df.groupby("vm_uuid")["memory_used"]
              .rolling(w, min_periods=1)
              .max()
              .reset_index(level=0, drop=True)
        )

    lag_cols = [c for c in df.columns if c.startswith("memory_lag_")]
    df = df.dropna(subset=lag_cols)

    return df.sort_values(["vm_uuid", "timestamp"]).reset_index(drop=True)
