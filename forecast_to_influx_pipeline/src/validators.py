# src/validators.py

import pandas as pd
from datetime import timezone

from src.logger import get_logger

logger = get_logger("validators")

# ============================================================
# REQUIRED COLUMNS FOR INFLUX WRITE
# ============================================================
MANDATORY_COLS = {
    "vm_uuid",
    "timestamp"
}


# ============================================================
# BASIC VALIDATIONS
# ============================================================
def validate_dataframe_not_empty(df: pd.DataFrame, name: str = "DataFrame"):
    if df.empty:
        raise ValueError(f"{name} is empty")


def validate_timestamp_column(df: pd.DataFrame):
    if "timestamp" not in df.columns:
        raise ValueError("Missing required column: timestamp")

    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        raise ValueError("timestamp column must be datetime")

    # Ensure UTC
    if df["timestamp"].dt.tz is None:
        logger.warning("timestamp is tz-naive — localizing to UTC")
        df["timestamp"] = df["timestamp"].dt.tz_localize(timezone.utc)


def validate_vm_uuid(df: pd.DataFrame):
    if "vm_uuid" not in df.columns:
        raise ValueError("Missing required column: vm_uuid")

    if df["vm_uuid"].isnull().any():
        raise ValueError("vm_uuid contains null values")


# ============================================================
# FORECAST-SPECIFIC VALIDATION
# ============================================================
def validate_forecast_payload(
    df: pd.DataFrame,
    forecast_field: str
):
    validate_dataframe_not_empty(df, "Forecast DataFrame")
    validate_timestamp_column(df)
    validate_vm_uuid(df)

    if forecast_field not in df.columns:
        raise ValueError(
            f"Missing forecast field: {forecast_field}"
        )

    if not pd.api.types.is_numeric_dtype(df[forecast_field]):
        raise ValueError(
            f"{forecast_field} must be numeric"
        )

    logger.info(
        f"Forecast payload validated | rows={len(df)} | "
        f"VMs={df['vm_uuid'].nunique()}"
    )


# ============================================================
# OPTIONAL METADATA VALIDATION (SOFT)
# ============================================================
def validate_optional_metadata(df: pd.DataFrame):
    optional_cols = [
        "run_date",
        "model_name",
        "horizon_minutes"
    ]

    for col in optional_cols:
        if col in df.columns:
            if df[col].isnull().any():
                logger.warning(f"Optional column {col} has null values")


# ============================================================
# SINGLE ENTRYPOINT
# ============================================================
def validate_before_influx_write(
    df: pd.DataFrame,
    forecast_field: str,
    run_date: str | None = None
):
    validate_forecast_payload(df, forecast_field)
    validate_optional_metadata(df)

    if run_date and "run_date" in df.columns:
        unique_dates = set(df["run_date"].astype(str))
        if unique_dates != {run_date}:
            raise ValueError(
                f"run_date mismatch — expected={run_date}, found={unique_dates}"
            )
