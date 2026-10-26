# src/train.py

import os
import numpy as np
import pandas as pd
import lightgbm as lgb
from typing import Dict, List
from src.logger import get_logger

logger = get_logger("train")

# ============================================================
# METRICS
# ============================================================
def compute_metrics(y_true, y_pred) -> Dict[str, float]:
    return {
        "mae": np.mean(np.abs(y_true - y_pred)),
        "rmse": np.sqrt(np.mean((y_true - y_pred) ** 2))
    }


# ============================================================
# BASELINE (LAG-1)
# ============================================================
def baseline_predict(df: pd.DataFrame, target_col: str) -> np.ndarray:
    return df.groupby("vm_uuid")[target_col].shift(1).values


# ============================================================
# GLOBAL LIGHTGBM TRAINING (CPU or MEMORY)
# ============================================================
def train_lgb_model(
    df_feat: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    model_name: str
) -> lgb.Booster:
    """
    Trains ONE global model across ALL VMs.

    CPU:
      target = cpu_used - cpu_daily_profile

    MEMORY:
      (not recommended – deterministic preferred)
    """

    logger.info(f"🚀 Training global LightGBM | target={target_col}")

    df = (
        df_feat
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # TARGET
    # --------------------------------------------------------
    if target_col == "cpu_used":
        if "cpu_daily_profile" not in df.columns:
            raise ValueError("cpu_daily_profile missing")

        y = (df["cpu_used"] - df["cpu_daily_profile"]).values
        logger.info("🎯 CPU residual learning enabled")
    else:
        y = df[target_col].values

    X = df[feature_cols]

    # --------------------------------------------------------
    # TIME-BASED GLOBAL SPLIT
    # --------------------------------------------------------
    split_ts = df["timestamp"].quantile(0.8)

    train_mask = df["timestamp"] <= split_ts
    val_mask = df["timestamp"] > split_ts

    X_train, X_val = X[train_mask], X[val_mask]
    y_train, y_val = y[train_mask], y[val_mask]

    logger.info(
        f"Train rows={len(X_train)} | Val rows={len(X_val)}"
    )

    # --------------------------------------------------------
    # SAMPLE WEIGHTING (CPU SPIKES)
    # --------------------------------------------------------
    if target_col == "cpu_used":
        spike_threshold = np.quantile(np.abs(y_train), 0.9)
        weights = 1.0 + 4.0 * (np.abs(y_train) > spike_threshold)
        train_weights = weights.astype(float)
        logger.info("⚡ Spike-aware weighting enabled")
    else:
        train_weights = None

    # --------------------------------------------------------
    # DATASETS
    # --------------------------------------------------------
    dtrain = lgb.Dataset(X_train, y_train, weight=train_weights)
    dval = lgb.Dataset(X_val, y_val, reference=dtrain)

    # --------------------------------------------------------
    # PARAMETERS
    # --------------------------------------------------------
    params = {
        "objective": "huber" if target_col == "cpu_used" else "regression",
        "metric": "mae",
        "learning_rate": 0.03,
        "num_leaves": 63,
        "min_data_in_leaf": 200,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.9,
        "bagging_freq": 5,
        "verbosity": -1,
        "seed": 42
    }

    # --------------------------------------------------------
    # TRAIN
    # --------------------------------------------------------
    model = lgb.train(
        params,
        dtrain,
        num_boost_round=800,
        valid_sets=[dtrain, dval],
        valid_names=["train", "val"],
        callbacks=[
            lgb.early_stopping(stopping_rounds=80),
            lgb.log_evaluation(50)
        ]
    )

    logger.info(f"✅ Best iteration={model.best_iteration}")
    return model


# ============================================================
# SAVE MODEL
# ============================================================
def save_lgb_model(
    model: lgb.Booster,
    run_date: str,
    model_name: str,
    model_dir: str = "models"
) -> str:
    os.makedirs(model_dir, exist_ok=True)
    path = os.path.join(model_dir, f"lgb_{model_name}_model_{run_date}.txt")
    model.save_model(path)
    logger.info(f"Model saved: {path}")
    return path


# ============================================================
# EVALUATION (GLOBAL)
# ============================================================
def evaluate_models(
    df_test: pd.DataFrame,
    feature_cols: List[str],
    model: lgb.Booster,
    target_col: str
) -> pd.DataFrame:

    logger.info(f"📊 Evaluating model | target={target_col}")

    df = df_test.copy()
    X = df[feature_cols]

    if target_col == "cpu_used":
        y_true = df["cpu_used"].values
        y_pred = model.predict(X) + df["cpu_daily_profile"].values
    else:
        y_true = df[target_col].values
        y_pred = model.predict(X)

    rows = []

    for vm, g in df.groupby("vm_uuid"):
        idx = g.index
        base = compute_metrics(
            y_true[idx],
            baseline_predict(g, target_col)
        )
        ml = compute_metrics(y_true[idx], y_pred[idx])

        rows.append({
            "vm_uuid": vm,
            "baseline_mae": base["mae"],
            "lgb_mae": ml["mae"],
            "mae_improvement_%": (
                (base["mae"] - ml["mae"]) / base["mae"] * 100
                if base["mae"] > 0 else 0
            )
        })

    result = pd.DataFrame(rows)
    logger.info(
        f"Avg MAE improvement={result['mae_improvement_%'].mean():.2f}%"
    )
    return result
