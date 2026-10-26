# 📊 Pipeline 3 – Forecast Sync (MinIO → InfluxDB)

## Overview

Pipeline 3 is the **final stage** of the VM Forecasting system. It reads forecasted CPU and Memory data from MinIO and writes it back into the InfluxDB monitoring bucket as new forecast fields within existing measurements.

This pipeline ensures forecasted values are available alongside actual metrics in InfluxDB for monitoring, alerting, and visualization purposes.

## 🎯 Objectives

* Read forecasted data from MinIO
* Validate forecast data schema and quality
* Map forecast schema to InfluxDB format
* Write forecast values into existing InfluxDB measurements
* Maintain idempotent writes using run-date state tracking
* Enable seamless integration with monitoring dashboards

## 🏗️ High-Level Architecture
```
┌────────────────────┐
│   MinIO Data Lake  │
│  forecasted-data/  │
│  ├── cpu_forecast  │
│  └── memory_forecast│
└──────────┬─────────┘
           │
           ▼
┌────────────────────┐
│ Forecast Sync      │
│ Pipeline           │
│ - Validation       │
│ - Schema Mapping   │
│ - State Check      │
└──────────┬─────────┘
           │
           ▼
┌────────────────────┐
│    InfluxDB        │
│ Monitoring Bucket  │
│  cpu_usage         │
│  └── cpu_used_forecast
│  memory_usage      │
│  └── memory_used_forecast
└────────────────────┘
```

## 🧩 What This Pipeline Does

### 1️⃣ Forecast Data Reading

* Reads forecasted parquet files from MinIO
* Locates files based on run date pattern
* Files read:
  * `cpu_forecast_YYYY-MM-DD.parquet`
  * `memory_forecast_YYYY-MM-DD.parquet`
* Validates file availability before processing

### 2️⃣ Data Validation

* Schema validation:
  * Required columns present
  * Correct data types
  * No missing critical fields
* Data quality checks:
  * Timestamp validity (UTC)
  * Forecast values within reasonable ranges
  * VM UUID format consistency
* Logs validation results and failures

### 3️⃣ Schema Mapping

* Maps forecast data to InfluxDB format
* Converts forecast schema to InfluxDB points
* Maintains consistency with existing measurements
* Schema mapping:

| Forecast Column | InfluxDB Field | InfluxDB Measurement |
|-----------------|----------------|---------------------|
| `cpu_used_forecast` | `cpu_used_forecast` | `cpu_usage` |
| `memory_used_forecast` | `memory_used_forecast` | `memory_usage` |
| `vm_uuid` | Tag: `vm_uuid` | Both measurements |
| `timestamp` | Time field | Both measurements |

### 4️⃣ State Management (Idempotency)

* Tracks synced run dates in local state file
* State file location: `data/state/forecast_sync_state.json`
* Prevents duplicate writes for the same run date
* Safe re-run capability:
  * Already synced runs are skipped
  * Only new forecasts are written
* State file structure:
```json
{
  "last_synced_runs": [
    "2025-07-26",
    "2025-07-27"
  ],
  "last_sync_timestamp": "2025-07-28T10:30:00Z"
}
```

### 5️⃣ InfluxDB Write Operations

* Writes forecast data to existing measurements
* Creates new forecast fields within measurements
* Supports future timestamps (forecast horizon)
* Write characteristics:
  * Synchronous writes for data integrity
  * Batch writes for performance
  * Automatic retry on transient failures
* Does NOT overwrite actual metrics
* Preserves all existing data

## 📁 Project Structure
```
forecast_to_influx_pipeline/
│
├── run_forecast_sync.py          # Pipeline entrypoint
├── README.md                      # This documentation
├── requirements.txt               # Python dependencies
│
├── logs/                          # Runtime logs
│   └── forecast_sync_YYYY-MM-DD.log
│
├── data/
│   └── state/
│       └── forecast_sync_state.json  # Idempotency state
│
├── config/
│   ├── minio.yaml                # MinIO connection config
│   └── influxdb.yaml             # InfluxDB connection config
│
└── src/
    ├── __init__.py
    ├── logger.py                 # Centralized logging
    ├── utils.py                  # Shared utilities
    ├── minio_reader.py           # Read forecast from MinIO
    ├── schema_mapper.py          # Map forecast schema
    ├── validators.py             # Data validation
    ├── influx_writer.py          # Write forecast to InfluxDB
    └── state_manager.py          # Idempotency tracking
```

## 📦 Input Data (MinIO)

### Location
```
<bucket>/influxdb/monitoring-data/forecasted-data/
```

### File Naming Convention
```
cpu_forecast_YYYY-MM-DD.parquet
memory_forecast_YYYY-MM-DD.parquet
```

### Required Schema

| Column | Type | Description |
|--------|------|-------------|
| `vm_uuid` | string | VM identifier (becomes tag) |
| `timestamp` | datetime | Forecast timestamp (UTC) |
| `cpu_used_forecast` | float | CPU forecast value |
| `memory_used_forecast` | float | Memory forecast value |
| `horizon_minutes` | int | Forecast horizon in minutes |
| `model_name` | string | Model identifier |
| `run_date` | date | Forecast run date |

## 🗄️ Output Data (InfluxDB)

### Target Bucket
```
monitoring-bucket
```

### Measurements & Fields

| Measurement | Existing Field | New Forecast Field |
|------------|----------------|-------------------|
| `cpu_usage` | `cpu_used` | `cpu_used_forecast` |
| `memory_usage` | `memory_used` | `memory_used_forecast` |

### Tags

* `vm_uuid` – VM identifier

### Time Field

* Uses forecast timestamps
* Supports future timestamps (beyond current time)
* All timestamps in UTC

## ⚙️ Configuration Files

### `config/minio.yaml`
```yaml
minio:
  endpoint: adc-ecos.enlightcloud.com
  access_key: <ACCESS_KEY>
  secret_key: <SECRET_KEY>
  secure: true
  bucket: 6189-enlight-ai-datalake
  prefix: influxdb/monitoring-data
```

### `config/influxdb.yaml`
```yaml
influxdb:
  url: https://<INFLUX_URL>
  org: <ORG>
  bucket: monitoring-bucket
  token_env: INFLUXDB_TOKEN
```

**Note:** InfluxDB token is read from environment variable for security.

### Environment Variables
```bash
export INFLUXDB_TOKEN=your_influxdb_token_here
```

## 🚀 How to Run

### 1️⃣ Create Virtual Environment
```bash
python -m venv forecast_sync_venv
source forecast_sync_venv/bin/activate  # On Windows: forecast_sync_venv\Scripts\activate
```

### 2️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install influxdb-client minio pandas pyarrow pyyaml
```

### 3️⃣ Set Environment Variables
```bash
export INFLUXDB_TOKEN=your_token_here
```

### 4️⃣ Run Pipeline
```bash
python run_forecast_sync.py
```

### 5️⃣ Monitor Logs
```bash
tail -f logs/forecast_sync_$(date +%Y-%m-%d).log
```

## 📊 Logging & Observability

The pipeline logs:

* Pipeline start & completion timestamps
* Files read from MinIO
* Validation results (pass/fail per metric)
* Row counts written to InfluxDB
* State management actions
* Skipped runs (already synced)
* Error details with stack traces
* Performance metrics (write duration)

### Log Levels

* **INFO** – Normal operations
* **WARNING** – Validation issues, skipped runs
* **ERROR** – Write failures, connection issues
* **DEBUG** – Detailed processing information

## 🔍 Verification in InfluxDB

### ⚠️ Important: Forecast Data is in the Future

Forecast timestamps are in the future, so InfluxDB UI's default time range won't show them.

### Verification Query (Flux)

#### CPU Forecast
```flux
from(bucket: "monitoring-bucket")
  |> range(start: 2026-01-22T00:00:00Z, stop: 2026-02-10T00:00:00Z)
  |> filter(fn: (r) => r._measurement == "cpu_usage")
  |> filter(fn: (r) => r._field == "cpu_used_forecast")
  |> limit(n: 10)
```

#### Memory Forecast
```flux
from(bucket: "monitoring-bucket")
  |> range(start: 2026-01-22T00:00:00Z, stop: 2026-02-10T00:00:00Z)
  |> filter(fn: (r) => r._measurement == "memory_usage")
  |> filter(fn: (r) => r._field == "memory_used_forecast")
  |> limit(n: 10)
```

#### Compare Actual vs Forecast
```flux
from(bucket: "monitoring-bucket")
  |> range(start: 2026-01-22T00:00:00Z, stop: 2026-02-10T00:00:00Z)
  |> filter(fn: (r) => r._measurement == "cpu_usage")
  |> filter(fn: (r) => r._field == "cpu_used" or r._field == "cpu_used_forecast")
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
```

## 🔄 State Management & Re-runs

### Check Current State
```bash
cat data/state/forecast_sync_state.json
```

### Force Re-sync (Reset State)
```bash
rm data/state/forecast_sync_state.json
python run_forecast_sync.py
```

### Sync Specific Run Date

Modify `run_forecast_sync.py` to specify run date:
```python
TARGET_RUN_DATE = "2025-07-26"  # Override default (today)
```

## ⚠️ Troubleshooting

| Issue | Possible Cause | Solution |
|-------|----------------|----------|
| No data visible in UI | Time range doesn't include future | Expand time range to include forecast horizon |
| Pipeline skips execution | Run date already synced | Check state file; delete to force re-sync |
| Forecast fields not visible | Fields not selected in UI query | Explicitly select forecast fields in query |
| Connection timeout | InfluxDB/MinIO unreachable | Verify network connectivity and credentials |
| Schema validation fails | Forecast data missing columns | Check Pipeline 2 output format |
| Duplicate data written | State file corrupted/deleted | Don't delete state file during active runs |

## ✅ Key Benefits

* **Non-destructive** – Does not overwrite actual metrics
* **Idempotent** – Safe to re-run without data duplication
* **Scalable** – Handles thousands of VMs efficiently
* **Production-ready** – Comprehensive logging and error handling
* **Dashboard-ready** – Forecast data available for Grafana/InfluxDB UI
* **State-aware** – Tracks sync history for audit and replay

## 🔗 Pipeline Dependencies

### Input from:

* **Pipeline 2** – ML forecasting pipeline outputs in MinIO

### Outputs to:

* **InfluxDB** – Monitoring bucket with forecast fields
* **Dashboards** – Grafana/InfluxDB UI for visualization
* **Alerting** – InfluxDB alerting rules on forecast thresholds

## 📌 Future Enhancements

* **Force Overwrite Mode** – Command-line flag to overwrite existing forecasts
* **Grafana Dashboards** – Pre-built templates for Actual vs Forecast visualization
* **Retention Policies** – Auto-cleanup of old forecast data
* **Backfill Support** – Ability to sync historical forecast runs
* **Rollback Capability** – Remove specific forecast runs
* **SLA Monitoring** – Forecast freshness alerts
* **Batch Mode** – Sync multiple run dates in one execution
* **Metrics Export** – Prometheus metrics for pipeline health

## 🧠 Summary

Pipeline 3 completes the VM forecasting system by seamlessly integrating ML-generated forecasts back into the operational monitoring infrastructure. It ensures forecast data is available alongside actual metrics, enabling proactive monitoring, capacity planning, and anomaly detection while maintaining data integrity and operational safety through robust state management and validation.

---

**Pipeline Sequence:**
1. **Pipeline 1** – InfluxDB → MinIO (Data Ingestion)
2. **Pipeline 2** – ML Processing & Forecasting
3. **Pipeline 3** – MinIO → InfluxDB (Forecast Sync) ← *You are here*