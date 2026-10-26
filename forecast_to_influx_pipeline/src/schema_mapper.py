# src/schema_mapper.py

import pandas as pd
from typing import Dict

from src.logger import get_logger

logger = get_logger("schema_mapper")

# ============================================================
# FORECAST TYPE → MEASUREMENT & FIELD MAP
# ============================================================
FORECAST_SCHEMA_MAP: Dict[str, Dict[str, str]] = {
    "cpu": {
        "measurement": "cpu_usage",
        "forecast_field": "cpu_used_forecast",
        "source_field": "cpu_used_forecast"
    },
    "memory": {
        "measurement": "memory_usage",
        "forecast_field": "memory_used_forecast",
        "source_field": "memory_used_forecast"
    }
    # Future-safe:
    # "disk": {
    #     "measurement": "disk_usage",
    #     "forecast_field": "disk_used_forecast",
    #     "source_field": "disk_used_forecast"
    # }
}

# ============================================================
# REQUIRED BASE COLUMNS (COMMON)
# ============================================================
BASE_REQUIRED_COLS = {
    "vm_uuid",
    "timestamp",
    "model_name",
    "run_date",
    "horizon_minutes"
}


# ============================================================
# VALIDATE FORECAST DATAFRAME
# ============================================================
def validate_forecast_df(
    df: pd.DataFrame,
    forecast_type: str
):
    """
    Ensures forecast DataFrame has required columns
    """
    if df.empty:
        raise ValueError("Forecast DataFrame is empty")

    if forecast_type not in FORECAST_SCHEMA_MAP:
        raise ValueError(
            f"Unsupported forecast_type='{forecast_type}'"
        )

    schema = FORECAST_SCHEMA_MAP[forecast_type]

    required_cols = BASE_REQUIRED_COLS | {schema["source_field"]}
    missing = required_cols - set(df.columns)

    if missing:
        raise ValueError(
            f"Forecast DataFrame missing columns: {missing}"
        )


# ============================================================
# MAP CPU FORECAST
# ============================================================
def map_cpu_forecast(df: pd.DataFrame) -> pd.DataFrame:
    """
    Maps CPU forecast DataFrame to InfluxDB-ready structure
    """
    validate_forecast_df(df, "cpu")

    schema = FORECAST_SCHEMA_MAP["cpu"]

    out = df[[
        "vm_uuid",
        "timestamp",
        "model_name",
        "run_date",
        "horizon_minutes",
        schema["source_field"]
    ]].copy()

    out = out.rename(
        columns={schema["source_field"]: schema["forecast_field"]}
    )

    logger.info(
        f"CPU forecast mapped | rows={len(out)} | "
        f"VMs={out['vm_uuid'].nunique()}"
    )

    return out


# ============================================================
# MAP MEMORY FORECAST
# ============================================================
def map_memory_forecast(df: pd.DataFrame) -> pd.DataFrame:
    """
    Maps Memory forecast DataFrame to InfluxDB-ready structure
    """
    validate_forecast_df(df, "memory")

    schema = FORECAST_SCHEMA_MAP["memory"]

    out = df[[
        "vm_uuid",
        "timestamp",
        "model_name",
        "run_date",
        "horizon_minutes",
        schema["source_field"]
    ]].copy()

    out = out.rename(
        columns={schema["source_field"]: schema["forecast_field"]}
    )

    logger.info(
        f"Memory forecast mapped | rows={len(out)} | "
        f"VMs={out['vm_uuid'].nunique()}"
    )

    return out


# ============================================================
# GENERIC MAPPER (FUTURE-SAFE)
# ============================================================
def map_forecast(
    df: pd.DataFrame,
    forecast_type: str
) -> pd.DataFrame:
    """
    Generic forecast mapper (CPU / Memory / future types)
    """
    validate_forecast_df(df, forecast_type)

    schema = FORECAST_SCHEMA_MAP[forecast_type]

    out = df[[
        "vm_uuid",
        "timestamp",
        "model_name",
        "run_date",
        "horizon_minutes",
        schema["source_field"]
    ]].copy()

    out = out.rename(
        columns={schema["source_field"]: schema["forecast_field"]}
    )

    logger.info(
        f"{forecast_type.upper()} forecast mapped | rows={len(out)} | "
        f"VMs={out['vm_uuid'].nunique()}"
    )

    return out
