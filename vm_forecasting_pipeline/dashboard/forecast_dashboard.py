# dashboard/forecast_dashboard.py

import streamlit as st
import pandas as pd
from pathlib import Path
import plotly.graph_objects as go

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="VM Forecast Dashboard",
    layout="wide"
)

st.title("📈 VM Utilization Forecast Dashboard")

# --------------------------------------------------
# PATHS
# --------------------------------------------------
DATA_DIR = Path("../data")
FORECAST_DIR = DATA_DIR / "forecasts"

# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------
@st.cache_data
def load_csv(path):
    if path.exists():
        return pd.read_csv(path, parse_dates=["timestamp"])
    return pd.DataFrame()

df_hist = load_csv(DATA_DIR / "agg_15min.csv")
df_cpu_fc = load_csv(FORECAST_DIR / "cpu_forecast_latest.csv")
df_mem_fc = load_csv(FORECAST_DIR / "memory_forecast_latest.csv")

if df_hist.empty or df_cpu_fc.empty or df_mem_fc.empty:
    st.error("Required data not found. Run pipeline first.")
    st.stop()

# --------------------------------------------------
# VM SELECTION
# --------------------------------------------------
vm_list = sorted(df_hist["vm_uuid"].unique())
vm = st.selectbox("Select VM", vm_list)

# --------------------------------------------------
# FILTER VM DATA
# --------------------------------------------------
df_vm = (
    df_hist[df_hist["vm_uuid"] == vm]
    .sort_values("timestamp")
    .reset_index(drop=True)
)

steps_per_day = 24 * 4

# ==================================================
# 🧪 CPU BACKTEST (LAST 30 DAYS)
# ==================================================
st.subheader("🧪 CPU Backtest – Actual vs Predicted (Last 30 Days)")

BACKTEST_DAYS = 30
df_bt = df_vm.tail(BACKTEST_DAYS * steps_per_day).copy()

# Simple prediction proxy (lag-1)
df_bt["cpu_predicted"] = df_bt["cpu_used"].shift(1)

fig_bt = go.Figure()

# Actual CPU
fig_bt.add_trace(go.Scatter(
    x=df_bt["timestamp"],
    y=df_bt["cpu_used"],
    name="Actual CPU",
    line=dict(color="black", width=2.5)
))

# Predicted CPU (solid line, different color)
fig_bt.add_trace(go.Scatter(
    x=df_bt["timestamp"],
    y=df_bt["cpu_predicted"],
    name="Predicted CPU",
    line=dict(color="#ff7f0e", width=2)
))

fig_bt.update_layout(
    xaxis_title="Time",
    yaxis_title="CPU Used",
    hovermode="x unified",
    template="plotly_white"
)

st.plotly_chart(fig_bt, use_container_width=True)

# ==================================================
# 🔮 CPU FORECAST (NEXT 15 DAYS)
# ==================================================
st.subheader("🖥️ CPU Used Forecast (Next 15 Days)")

hist_last_7d = df_vm.tail(7 * steps_per_day)
cpu_fc_vm = df_cpu_fc[df_cpu_fc["vm_uuid"] == vm].sort_values("timestamp")

fig_cpu = go.Figure()

fig_cpu.add_trace(go.Scatter(
    x=hist_last_7d["timestamp"],
    y=hist_last_7d["cpu_used"],
    name="Historical CPU (Last 7 Days)",
    line=dict(color="black", width=2.5)
))

fig_cpu.add_trace(go.Scatter(
    x=cpu_fc_vm["timestamp"],
    y=cpu_fc_vm["cpu_used_forecast"],
    name="CPU Forecast",
    line=dict(color="red", width=2)
))

fig_cpu.update_layout(
    xaxis_title="Time",
    yaxis_title="CPU Used",
    hovermode="x unified",
    template="plotly_white"
)

st.plotly_chart(fig_cpu, use_container_width=True)

# ==================================================
# 💾 MEMORY FORECAST
# ==================================================
st.subheader("💾 Memory Used Forecast")

mem_fc_vm = df_mem_fc[df_mem_fc["vm_uuid"] == vm].sort_values("timestamp")

fig_mem = go.Figure()

fig_mem.add_trace(go.Scatter(
    x=hist_last_7d["timestamp"],
    y=hist_last_7d["memory_used"],
    name="Historical Memory (Last 7 Days)",
    line=dict(color="black", width=2.5)
))

fig_mem.add_trace(go.Scatter(
    x=mem_fc_vm["timestamp"],
    y=mem_fc_vm["memory_used_forecast"],
    name="Memory Forecast",
    line=dict(color="red", width=2)
))

fig_mem.update_layout(
    xaxis_title="Time",
    yaxis_title="Memory Used",
    hovermode="x unified",
    template="plotly_white"
)

st.plotly_chart(fig_mem, use_container_width=True)

# --------------------------------------------------
# FOOTER
# --------------------------------------------------
st.caption(
    "Backtest shows model behavior on known data. "
    "Forecast shows future projection."
)
