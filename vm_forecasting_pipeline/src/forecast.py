# src/forecast.py

import pandas as pd
import numpy as np
from collections import deque
from src.logger import get_logger

logger = get_logger("forecast")

# ============================================================
# FORECAST (CPU = ML, MEMORY = DETERMINISTIC)
# ============================================================
def forecast_lgb_15min(
    model,
    df_features: pd.DataFrame,
    feature_cols: list,
    target_col: str,
    horizon_steps: int,
    run_date: str,
    model_name: str
) -> pd.DataFrame:
    """
    Forecasts at 15-minute resolution.

    CPU  : Recursive ML forecasting
    MEM  : Deterministic (last value carried forward)

    Returns:
      DataFrame with forecasted values
    """

    logger.info(
        f"🧠 Forecasting target={target_col} | horizon_steps={horizon_steps}"
    )

    if df_features.empty:
        raise ValueError("df_features is empty — cannot forecast")

    # ============================================================
    # MEMORY → DETERMINISTIC FORECAST
    # ============================================================
    if target_col == "memory_used":
        forecasts = []

        for vm, g in df_features.groupby("vm_uuid"):
            g = g.sort_values("timestamp")

            last_row = g.iloc[-1]
            base_ts = last_row["timestamp"]
            last_value = last_row["memory_used"]

            for step in range(1, horizon_steps + 1):
                ts = base_ts + pd.Timedelta(minutes=15 * step)

                forecasts.append({
                    "vm_uuid": vm,
                    "timestamp": ts,
                    "memory_used_forecast": last_value,
                    "model_name": model_name,
                    "run_date": run_date,
                    "horizon_minutes": step * 15
                })

        logger.info(
            f"✅ Memory forecast completed | rows={len(forecasts)}"
        )

        return pd.DataFrame(forecasts)

    # ============================================================
    # CPU → RECURSIVE ML FORECAST
    # ============================================================
    if model is None:
        raise ValueError("CPU forecasting requires a trained model")

    forecasts = []

    for vm, g in df_features.groupby("vm_uuid"):
        g = g.sort_values("timestamp").reset_index(drop=True)

        # Require at least 1 week of history (672 points)
        if len(g) < 672:
            logger.warning(
                f"Skipping VM {vm} — insufficient history ({len(g)} rows)"
            )
            continue

        history = g.tail(672).copy()
        lag_queue = deque(history["cpu_used"].values, maxlen=672)

        base_ts = history.iloc[-1]["timestamp"]

        for step in range(1, horizon_steps + 1):
            ts = base_ts + pd.Timedelta(minutes=15 * step)

            hour = ts.hour
            minute_bucket = ts.minute // 15
            dow = ts.dayofweek
            is_weekend = int(dow >= 5)

            # -------- Daily profile lookup --------
            profile = history[
                (history["hour"] == hour) &
                (history["minute_bucket"] == minute_bucket)
            ]["cpu_used"].median()

            if np.isnan(profile):
                profile = history["cpu_used"].mean()

            last_96 = np.array(lag_queue)[-96:]
            last_24 = np.array(lag_queue)[-24:]

            row = {
                "hour": hour,
                "minute_bucket": minute_bucket,
                "day_of_week": dow,
                "is_weekend": is_weekend,
                "cpu_daily_profile": profile,
                "cpu_lag_1": lag_queue[-1],
                "cpu_lag_2": lag_queue[-2],
                "cpu_lag_4": lag_queue[-4],
                "cpu_lag_8": lag_queue[-8],
                "cpu_lag_16": lag_queue[-16],
                "cpu_lag_96": lag_queue[-96],
                "cpu_lag_672": lag_queue[0],
                "cpu_roll_mean_4": last_24[-4:].mean(),
                "cpu_roll_max_4": last_24[-4:].max(),
                "cpu_roll_mean_24": last_24.mean(),
                "cpu_roll_max_24": last_24.max(),
                "cpu_std_24h": last_96.std(),
                "cpu_p95_24h": np.percentile(last_96, 95),
                "cpu_active_ratio_24h": (last_96 > 0.1).mean(),
                "cpu_is_spike": int(
                    last_96[-1] > np.percentile(last_96, 95)
                ),
            }

            X = pd.DataFrame([row])[feature_cols]

            residual = model.predict(X)[0]
            cpu_pred = np.clip(
                profile + residual,
                0,
                row["cpu_p95_24h"] * 1.3
            )

            # Update lag queue
            lag_queue.append(cpu_pred)

            # Extend history (for profile lookup)
            history = pd.concat(
                [history, pd.DataFrame([{
                    "timestamp": ts,
                    "cpu_used": cpu_pred,
                    "hour": hour,
                    "minute_bucket": minute_bucket
                }])],
                ignore_index=True
            ).tail(672)

            forecasts.append({
                "vm_uuid": vm,
                "timestamp": ts,
                "cpu_used_forecast": cpu_pred,
                "model_name": model_name,
                "run_date": run_date,
                "horizon_minutes": step * 15
            })

    logger.info(
        f"✅ CPU forecast completed | rows={len(forecasts)}"
    )

    return pd.DataFrame(forecasts)
