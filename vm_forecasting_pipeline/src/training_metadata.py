# src/training_metadata.py

import pandas as pd
import uuid
from pathlib import Path
from datetime import datetime


# ============================================================
# WRITE TRAINING METADATA
# ============================================================
def write_training_metadata(
    run_date: str,
    train_start_time: datetime,
    train_end_time: datetime,

    total_vms_seen: int,
    vms_eligible: int,
    vms_trained: int,
    vms_dropped: int,

    train_data_start: str,
    train_data_end: str,
    forecast_start: str,
    forecast_end: str,

    cpu_metrics_df: pd.DataFrame,

    status: str,
    remarks: str = "",
    model_path: str | None = None
) -> str:
    """
    Stores training metadata for each pipeline run.
    Appends to data/training_metadata.csv
    """

    metadata_dir = Path("data")
    metadata_dir.mkdir(exist_ok=True)

    metadata_path = metadata_dir / "training_metadata.csv"

    run_id = str(uuid.uuid4())

    record = {
        "run_id": run_id,
        "run_date": run_date,

        "train_start_time": train_start_time,
        "train_end_time": train_end_time,
        "train_duration_sec": (
            train_end_time - train_start_time
        ).total_seconds(),

        "total_vms_seen": total_vms_seen,
        "vms_eligible": vms_eligible,
        "vms_trained": vms_trained,
        "vms_dropped": vms_dropped,

        "train_data_start": train_data_start,
        "train_data_end": train_data_end,
        "forecast_start": forecast_start,
        "forecast_end": forecast_end,

        "model_path": model_path,
        "status": status,
        "remarks": remarks,

        "created_at": datetime.utcnow()
    }

    meta_df = pd.DataFrame([record])

    if metadata_path.exists():
        existing = pd.read_csv(metadata_path)
        meta_df = pd.concat([existing, meta_df], ignore_index=True)

    meta_df.to_csv(metadata_path, index=False)

    # -------------------------------
    # Save per-run metrics (optional)
    # -------------------------------
    metrics_dir = metadata_dir / "metrics_history"
    metrics_dir.mkdir(exist_ok=True)

    cpu_metrics_df["run_id"] = run_id
    cpu_metrics_df["run_date"] = run_date

    cpu_metrics_df.to_csv(
        metrics_dir / f"cpu_metrics_{run_date}.csv",
        index=False
    )

    return run_id
