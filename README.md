# 🚀 VM Forecasting Service

## Overview

Automated **CPU and Memory forecasting** for virtual machines. Ingests monitoring data, trains ML models, and syncs predictions to InfluxDB.

## 📁 Service Structure
```
forecast-service/
├── fetch_data_pipeline/           # Pipeline 1: InfluxDB → MinIO
├── vm_forecasting_pipeline/       # Pipeline 2: ML Training & Forecasting
└── forecast_to_influx_pipeline/   # Pipeline 3: MinIO → InfluxDB
```

## 🔄 Pipeline Flow
```
InfluxDB (Raw Data)
       ↓
Pipeline 1: Fetch Data
- Fetch VM metrics from InfluxDB
- Validate 90-day history
- Store in MinIO (180-day window)
       ↓
Pipeline 2: ML Forecasting
- Process & aggregate data
- Train LightGBM models
- Generate 15-day forecasts
       ↓
Pipeline 3: Forecast Sync
- Read forecasts from MinIO
- Write to InfluxDB
- Enable dashboard visibility
       ↓
InfluxDB (Forecasts)
```

## 📋 Pipeline Summary

| Pipeline | Input | Output | Purpose |
|----------|-------|--------|---------|
| **fetch_data_pipeline** | InfluxDB metrics | Raw data in MinIO | Ingest VM monitoring data |
| **vm_forecasting_pipeline** | MinIO raw data | Forecasts in MinIO | Train models & predict |
| **forecast_to_influx_pipeline** | MinIO forecasts | InfluxDB forecast fields | Sync to dashboards |

## 🎯 Key Features

✅ **10,000+ VMs** – Handles large-scale deployments  
✅ **15-day forecasts** – Long-term capacity planning  
✅ **Incremental updates** – Only processes new data  
✅ **Dashboard-ready** – View in Grafana/InfluxDB UI  
✅ **Production-grade** – Logging, error handling, state management  

## 🚀 Quick Start

1. **Configure connections** – Update `configs/*.yaml` in each pipeline
2. **Run pipelines in sequence:**
```bash
   cd fetch_data_pipeline && python run_pipeline.py
   cd vm_forecasting_pipeline && python run_pipeline.py
   cd forecast_to_influx_pipeline && python run_forecast_sync.py
```

Refer to individual pipeline READMEs for detailed setup.

## 📊 Outputs

**MinIO:**
- Raw data: `influxdb/monitoring-data/raw-data/`
- Forecasts: `influxdb/monitoring-data/forecasted-data/`

**InfluxDB:**
- New fields: `cpu_used_forecast`, `memory_used_forecast`

## 📞 Support

See individual pipeline READMEs for detailed documentation.

---

**Version:** 1.0 | **Last Updated:** January 2026