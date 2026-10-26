# 📥 Pipeline 1 – InfluxDB → MinIO Data Ingestion

## Overview

Pipeline 1 is responsible for ingesting VM monitoring data from InfluxDB and storing it in MinIO in a structured, scalable, and reusable format.

This pipeline acts as the data foundation for the entire forecasting system and is fully decoupled from preprocessing, model training, and forecasting logic.

## 🎯 Objectives

* Fetch VM-level CPU and Memory metrics from InfluxDB
* Validate VM data availability (minimum history requirement)
* Store data directly in MinIO (no local disk dependency)
* Maintain a rolling 180-day window of data
* Enable reuse for downstream ML pipelines

## 🧩 What This Pipeline Does

### 1️⃣ VM Eligibility Validation

* Reads VM list from `configs/vm_source.yaml`
* Checks historical availability per VM using InfluxDB
* Eligibility rules:
  * ✅ VM must have ≥ 90 days of historical data
  * ❌ VMs with < 90 days are dropped
* Logs:
  * Total VMs provided
  * Eligible VM count and list
  * Dropped VM count with reasons

### 2️⃣ Date Window Management

* Maintains a rolling window of 180 days
* First run:
  * Fetches the complete 180-day historical window
* Subsequent runs:
  * Fetches only missing / latest days
  * Automatically deletes data older than 180 days from MinIO

### 3️⃣ Data Fetching from InfluxDB

* Fetches data day-wise
* Metrics:
  * `cpu_used`
  * `memory_used`
* Measurements:
  * `cpu_usage`
  * `memory_usage`
* Data is fetched in VM batches to:
  * Avoid large Flux queries
  * Prevent InfluxDB timeouts
  * Support 10k+ VMs

### 4️⃣ Data Shaping & Consistency

* Ensures one row per VM per timestamp
* CPU and Memory metrics are aligned into a single row
* Missing metrics remain as `NaN`

Final schema:

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | datetime | UTC timestamp |
| `vm_uuid` | string | Unique VM identifier |
| `cpu_used` | float | CPU usage value |
| `memory_used` | float | Memory usage value |

### 5️⃣ Storage in MinIO

* Data is stored day-wise in MinIO
* No local data storage
* Directory structure inside MinIO:
```
6189-enlight-ai-datalake/
└── influxdb/
    └── monitoring-data/
        └── raw-data/
            ├── 2025-07-26/
            │   └── data.parquet
            ├── 2025-07-27/
            │   └── data.parquet
            └── ...
```

## 🔁 Incremental & Idempotent Design

* Pipeline can be safely re-run
* Already available days are skipped
* Only missing data is fetched
* Ensures:
  * No duplicate data
  * Minimal load on InfluxDB

## 📊 Logging & Observability

The pipeline logs:

* Pipeline start & completion
* VM eligibility summary
* Daily fetch progress
* Rows ingested per day
* Retention cleanup actions
* Failure points with stack traces

## ⚙️ Configuration Files

### `configs/influxdb.yaml`
```yaml
influxdb:
  url: <INFLUX_URL>
  token: <TOKEN>
  org: <ORG>
  bucket: <BUCKET_NAME>
```

### `configs/vm_source.yaml`
```yaml
vm_source:
  mode: static
  vm_list:
    - <vm_uuid_1>
    - <vm_uuid_2>
```

### `configs/minio.yaml`
```yaml
minio:
  endpoint: <MINIO_ENDPOINT>
  access_key: <ACCESS_KEY>
  secret_key: <SECRET_KEY>
  bucket: 6189-enlight-ai-datalake
```

## 🚀 How to Run
```bash
python run_pipeline.py
```

## ✅ Key Benefits

* **Scalable** – supports thousands of VMs
* **InfluxDB-safe** – avoids heavy historical re-queries
* **Reusable data layer** – raw data can be reused anytime
* **Production-ready** – clear separation of concerns
* **Fault-tolerant** – failures don't corrupt stored data

## 🔗 Downstream Usage

This pipeline feeds:

* **Pipeline 2** – preprocessing, aggregation, ML training & forecasting
* **Pipeline 3** – pushing forecasted data back into InfluxDB

## 🧠 Summary

Pipeline 1 transforms raw monitoring data ingestion into a robust, incremental, and scalable data platform, enabling reliable forecasting without stressing InfluxDB or reprocessing historical data repeatedly.