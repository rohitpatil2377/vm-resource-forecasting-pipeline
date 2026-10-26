from src.logger import get_logger
logger = get_logger("forecast_pipeline")

from datetime import datetime, UTC
import os
import time
import pandas as pd

# ---------------- Core ----------------
from src.minio_reader import fetch_and_store_raw_data
from src.preprocess import preprocess_raw_data
from src.aggregate import aggregate_to_15min

# ---------------- Feature builders ----------------
from src.features import (
    build_cpu_features,
    build_memory_features
)

# ---------------- ML (CPU ONLY) ----------------
from src.train import (
    train_lgb_model,
    evaluate_models,
    save_lgb_model
)

from src.forecast import forecast_lgb_15min
from src.write_forecast import (
    write_cpu_forecast,
    write_memory_forecast
)

from src.training_metadata import write_training_metadata


# =================================================
# CONFIG
# =================================================
RUN_DATE = datetime.now(UTC).date().isoformat()

FORECAST_DAYS = 15
HORIZON_STEPS = FORECAST_DAYS * 24 * 4  # 15-min steps

os.makedirs("models", exist_ok=True)
os.makedirs("data", exist_ok=True)


# =================================================
# PIPELINE START
# =================================================
pipeline_start = time.perf_counter()
pipeline_start_ts = datetime.now(UTC)

logger.info(
    f"PIPELINE_START | run_date={RUN_DATE} | ts={pipeline_start_ts.isoformat()} | timezone=UTC"
)

# ---- ONE-TIME TIMESTAMP STANDARD ----
logger.info(
    "TIMESTAMP_STANDARD | "
    "source=minio_parquet | "
    "dtype=datetime64[ns, UTC] | "
    "timezone=UTC"
)


# =================================================
# 1. FETCH RAW DATA (FROM MINIO)
# =================================================
step_start = time.perf_counter()

df_raw, vm_status = fetch_and_store_raw_data(run_date=RUN_DATE)

if df_raw.empty:
    raise RuntimeError("No data fetched from MinIO")

logger.info(
    f"FETCH_RAW | rows={len(df_raw)} | "
    f"vms={df_raw['vm_uuid'].nunique()} | "
    f"duration_seconds={time.perf_counter() - step_start:.2f}"
)


# =================================================
# 2. PREPROCESS (1-min)
# =================================================
step_start = time.perf_counter()

df_clean_1min, dropped_vms = preprocess_raw_data(df_raw)

logger.info(
    f"PREPROCESS | rows={len(df_clean_1min)} | "
    f"dropped_vms={len(dropped_vms)} | "
    f"duration_seconds={time.perf_counter() - step_start:.2f}"
)


# =================================================
# 3. AGGREGATE (15-min)
# =================================================
step_start = time.perf_counter()

df_15min = aggregate_to_15min(df_clean_1min)
df_15min.to_csv("data/agg_15min.csv", index=False)

logger.info(
    f"AGGREGATE_15MIN | rows={len(df_15min)} | "
    f"duration_seconds={time.perf_counter() - step_start:.2f}"
)


# =================================================
# 4. FEATURE ENGINEERING
# =================================================
step_start = time.perf_counter()

df_cpu = build_cpu_features(
    df_15min,
    lags=[1, 2, 4, 8, 16, 96],
    rolling_windows=[4, 24]
)

df_mem = build_memory_features(
    df_15min,
    lags=[1, 2, 4, 8, 16, 96],
    rolling_windows=[4, 24]
)

logger.info(
    f"FEATURE_ENGINEERING | duration_seconds={time.perf_counter() - step_start:.2f}"
)


# ---------------- FEATURE LISTS ----------------
cpu_features = [
    c for c in df_cpu.columns
    if (
        c.startswith("cpu_")
        and c not in ["cpu_used"]
    )
    or c in ["hour", "minute_bucket", "day_of_week", "is_weekend"]
]

mem_features = [
    c for c in df_mem.columns
    if c.startswith("memory_")
    or c in ["hour", "minute_bucket", "day_of_week", "is_weekend"]
]

logger.info(
    f"FEATURE_COUNTS | cpu={len(cpu_features)} | memory={len(mem_features)}"
)


# =================================================
# 5. TRAINING WINDOW (LAST 6 MONTHS PER VM)
# =================================================
def filter_training_window(df: pd.DataFrame, months: int = 6) -> pd.DataFrame:
    dfs = []
    for vm, g in df.groupby("vm_uuid"):
        last_ts = g["timestamp"].max()
        start_ts = last_ts - pd.DateOffset(months=months)
        g_train = g[g["timestamp"] >= start_ts]
        if len(g_train) > 500:
            dfs.append(g_train)
    return pd.concat(dfs, ignore_index=True)


step_start = time.perf_counter()

df_cpu_train = filter_training_window(df_cpu)

logger.info(
    f"TRAIN_WINDOW | rows={len(df_cpu_train)} | "
    f"vms={df_cpu_train['vm_uuid'].nunique()} | "
    f"duration_seconds={time.perf_counter() - step_start:.2f}"
)


# =================================================
# 6. TRAIN CPU MODEL
# =================================================
step_start = time.perf_counter()
train_start_time = datetime.now(UTC)

cpu_model = train_lgb_model(
    df_cpu_train,
    cpu_features,
    target_col="cpu_used",
    model_name="cpu"
)

cpu_metrics = evaluate_models(
    df_cpu_train,
    cpu_features,
    cpu_model,
    "cpu_used"
)

cpu_model_path = save_lgb_model(cpu_model, RUN_DATE, "cpu")
train_end_time = datetime.now(UTC)

logger.info(
    f"MODEL_TRAIN_CPU | model_path={cpu_model_path} | "
    f"train_start={train_start_time.isoformat()} | "
    f"train_end={train_end_time.isoformat()} | "
    f"duration_seconds={time.perf_counter() - step_start:.2f}"
)


# =================================================
# 7. FORECAST
# =================================================
step_start = time.perf_counter()

fc_cpu = forecast_lgb_15min(
    model=cpu_model,
    df_features=df_cpu,
    feature_cols=cpu_features,
    target_col="cpu_used",
    horizon_steps=HORIZON_STEPS,
    run_date=RUN_DATE,
    model_name="lgb_cpu"
)

fc_mem = forecast_lgb_15min(
    model=None,
    df_features=df_mem,
    feature_cols=mem_features,
    target_col="memory_used",
    horizon_steps=HORIZON_STEPS,
    run_date=RUN_DATE,
    model_name="deterministic_memory"
)

write_cpu_forecast(fc_cpu)
write_memory_forecast(fc_mem)

logger.info(
    f"FORECAST | horizon_steps={HORIZON_STEPS} | "
    f"duration_seconds={time.perf_counter() - step_start:.2f}"
)


# =================================================
# 8. METADATA
# =================================================
step_start = time.perf_counter()

run_id = write_training_metadata(
    run_date=RUN_DATE,
    train_start_time=train_start_time,
    train_end_time=train_end_time,
    total_vms_seen=df_15min["vm_uuid"].nunique(),
    vms_eligible=df_cpu_train["vm_uuid"].nunique(),
    vms_trained=df_cpu_train["vm_uuid"].nunique(),
    vms_dropped=len(dropped_vms),
    train_data_start=str(df_cpu_train["timestamp"].min()),
    train_data_end=str(df_cpu_train["timestamp"].max()),
    forecast_start=str(fc_cpu["timestamp"].min()),
    forecast_end=str(fc_cpu["timestamp"].max()),
    cpu_metrics_df=cpu_metrics,
    status="success"
)

logger.info(
    f"METADATA_WRITE | run_id={run_id} | "
    f"duration_seconds={time.perf_counter() - step_start:.2f}"
)


# =================================================
# PIPELINE END
# =================================================
pipeline_end_ts = datetime.now(UTC)

logger.info(
    f"PIPELINE_SUCCESS | run_id={run_id} | "
    f"total_duration_seconds={time.perf_counter() - pipeline_start:.2f} | "
    f"end_ts={pipeline_end_ts.isoformat()} | timezone=UTC"
)
