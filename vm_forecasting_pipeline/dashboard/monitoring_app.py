# dashboard/monitoring_app.py

import streamlit as st
import pandas as pd
from pathlib import Path
import plotly.express as px

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="ML Pipeline Monitoring",
    layout="wide"
)

st.title("🛠️ ML Pipeline Monitoring Dashboard")

# --------------------------------------------------
# PATHS
# --------------------------------------------------
DATA_DIR = Path("../data")
MONITOR_DIR = DATA_DIR / "monitoring"
LOG_DIR = Path("../logs")

# --------------------------------------------------
# HELPERS
# --------------------------------------------------
@st.cache_data
def load_csv(path):
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()

def safe_int(val):
    if pd.isna(val):
        return "N/A"
    try:
        return int(val)
    except Exception:
        return "N/A"

def safe_str(val):
    return "N/A" if pd.isna(val) else str(val)

# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------
train_meta = load_csv(DATA_DIR / "training_metadata.csv")
health_df = load_csv(MONITOR_DIR / "health_status.csv")
drift_df = load_csv(MONITOR_DIR / "drift_summary.csv")
cpu_err_df = load_csv(MONITOR_DIR / "cpu_error_daily.csv")

# --------------------------------------------------
# PIPELINE STATUS
# --------------------------------------------------
st.subheader("📌 Pipeline Status")

if train_meta.empty:
    st.warning("No training metadata found. Run pipeline first.")
else:
    last = train_meta.iloc[-1]

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Last Run Date", safe_str(last.get("run_date")))
    col2.metric("Status", safe_str(last.get("status")))
    col3.metric("VMs Trained", safe_int(last.get("vms_trained")))

    # Training duration (seconds)
    train_dur = last.get("train_duration_sec")
    col4.metric(
        "Training Time (sec)",
        round(train_dur, 2) if not pd.isna(train_dur) else "N/A"
    )

    col5.metric("Run ID", safe_str(last.get("run_id")))

# --------------------------------------------------
# TRAINING & FORECAST WINDOWS
# --------------------------------------------------
st.subheader("🕒 Training & Forecast Windows")

if not train_meta.empty:
    col1, col2 = st.columns(2)

    col1.markdown("### Training Window")
    col1.write(
        f"{safe_str(last.get('train_data_start'))} → "
        f"{safe_str(last.get('train_data_end'))}"
    )

    col1.metric(
        "Training Duration (days)",
        safe_int(last.get("training_window_days"))
    )

    col2.markdown("### Forecast Window")
    col2.write(
        f"{safe_str(last.get('forecast_start'))} → "
        f"{safe_str(last.get('forecast_end'))}"
    )

    col2.metric(
        "Forecast Horizon (days)",
        safe_int(last.get("forecast_horizon_days"))
    )

# --------------------------------------------------
# SYSTEM HEALTH
# --------------------------------------------------
st.subheader("🚦 System Health")

if not health_df.empty:
    latest_health = health_df.iloc[-1]

    status = safe_str(latest_health.get("status"))
    remarks = safe_str(latest_health.get("remarks"))

    color_map = {
        "GREEN": "🟢",
        "AMBER": "🟠",
        "RED": "🔴"
    }

    st.markdown(
        f"### {color_map.get(status, '⚪')} {status}"
    )
    st.write("Remarks:", remarks)
else:
    st.info("Health status not available")

# --------------------------------------------------
# DRIFT SUMMARY
# --------------------------------------------------
st.subheader("📉 Feature Drift Summary")

if not drift_df.empty:
    drift_display = drift_df.copy()

    if "drift_flag" in drift_display.columns:
        drift_display["drift_flag"] = drift_display["drift_flag"].map(
            {True: "YES", False: "NO"}
        )

    st.dataframe(drift_display, use_container_width=True)
else:
    st.info("No drift data available")

# --------------------------------------------------
# CPU ERROR TREND
# --------------------------------------------------
st.subheader("📈 CPU Accuracy Trend (MAE)")

if not cpu_err_df.empty:
    cpu_err_df["date"] = pd.to_datetime(cpu_err_df["date"], errors="coerce")

    fig = px.line(
        cpu_err_df,
        x="date",
        y="mae",
        color="vm_uuid",
        title="Daily CPU MAE Trend"
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("CPU error history not available")

# --------------------------------------------------
# PIPELINE LOG VIEWER
# --------------------------------------------------
st.subheader("📜 Pipeline Logs")

log_files = sorted(LOG_DIR.glob("pipeline_*.log"), reverse=True)

if log_files:
    selected_log = st.selectbox(
        "Select log file",
        log_files
    )

    with open(selected_log) as f:
        log_text = f.read()

    st.text_area(
        "Pipeline Log Output",
        log_text,
        height=400
    )
else:
    st.info("No logs found")

# --------------------------------------------------
# FOOTER
# --------------------------------------------------
st.caption(
    "Monitoring dashboard | "
    "Pipeline runs daily at 01:00 AM | "
    "Auto-updated from persisted artifacts"
)
