# 🤖 Pipeline 2 – Data Processing, Feature Engineering, Training & Forecasting

## Overview

Pipeline 2 is the **ML and analytics engine** of the VM monitoring and forecasting system. It reads 1-minute raw VM metrics stored in MinIO by Pipeline 1, performs comprehensive data validation, gap handling, aggregation, feature engineering, trains forecasting models, generates 15-minute resolution forecasts for a 15-day horizon, and writes all outputs back to MinIO.

This pipeline is **fully decoupled from InfluxDB** and operates entirely on data stored in MinIO, enabling scalable, reproducible, and auditable ML operations.

## 🎯 Objectives

* Convert raw monitoring data into model-ready time series
* Ensure data quality and consistency through validation and gap handling
* Capture seasonality, spikes, and regime behavior through feature engineering
* Train production-grade forecasting models (LightGBM for CPU)
* Generate 15-day forecasts at 15-minute resolution
* Persist forecasts, models, and metadata for downstream use and audit

## 🏗️ High-Level Architecture
```
┌────────────────────┐
│   MinIO Data Lake  │
│   raw-data/        │
│   (1-min metrics)  │
└──────────┬─────────┘
           │
           ▼
┌────────────────────┐
│  Pipeline 2        │
│  ├─ Preprocessing  │
│  ├─ Aggregation    │
│  ├─ Feature Eng.   │
│  ├─ Model Training │
│  ├─ Forecasting    │
│  └─ Validation     │
└──────────┬─────────┘
           │
           ▼
┌────────────────────┐
│   MinIO Data Lake  │
│  forecasted-data/  │
│  (15-min forecasts)│
└────────────────────┘
```

## 🧩 What This Pipeline Does

### 📥 Input Data (from MinIO)

#### Source Location
```
influxdb/monitoring-data/raw-data/
```

#### Data Characteristics

* **Frequency:** 1 minute
* **Metrics:**
  * `cpu_used`
  * `memory_used`
* **Format:** VM-wise time series
* **Validation:** Pre-validated for minimum 90-day history by Pipeline 1

#### 🔹 Important Note

Pipeline 1 fetches raw metrics at **1-minute resolution using MAX aggregation** from InfluxDB to preserve peak utilization. Pipeline 2 then applies appropriate smoothing for modeling purposes.

---

### 🧹 Step 1: Data Preprocessing

#### 1.1 Schema Validation

* Ensures required columns exist:
  * `timestamp`
  * `vm_uuid`
  * `cpu_used`
  * `memory_used`
* Validates data types and formats
* Rejects empty or malformed datasets early
* Logs validation results per VM

#### 1.2 Time Gap Detection

* Computes time differences between consecutive points per VM
* Identifies missing or irregular intervals
* Tracks maximum gap duration per VM
* Flags VMs with excessive gaps for handling

#### 1.3 Rule-Based Gap Filling (Per VM)

Different gap sizes are handled with appropriate strategies to maintain data quality:

| Gap Duration | Filling Strategy | Rationale |
|-------------|------------------|-----------|
| **1–5 min** | Forward + backward fill | Minimal disruption, recent values valid |
| **6–30 min** | Rolling 30-minute mean | Short-term smoothing |
| **31–120 min** | Rolling 60-minute mean | Medium-term context |
| **2–24 hours** | Diurnal (hour-of-day) mean | Leverage daily patterns |
| **> 24 hours** | **VM dropped** | Insufficient data quality |

**VMs with gaps greater than 1 day are removed entirely** to ensure forecast reliability.

#### 1.4 Missing Data Reporting

* **Before fill:** Missing data percentage per VM
* **After fill:** Remaining missing data percentage
* **VM drops:** Count and reasons
* **Summary statistics:** Logged for audit trail

---

### ⏱️ Step 2: Time Aggregation (1 min → 15 min)

#### Aggregation Rules

* **Target frequency:** 15 minutes
* **Aggregation function:** MEAN (per VM)
* **Window:** Fixed 15-minute buckets aligned to wall clock

| Metric | Aggregation Method | Purpose |
|--------|-------------------|---------|
| `cpu_used` | Mean | Smooth out noise while preserving trends |
| `memory_used` | Mean | Stable metric, mean is representative |

#### 🔹 Design Rationale

* **Pipeline 1:** Preserves peaks using MAX (safety-first ingestion)
* **Pipeline 2:** Applies smoothing via MEAN (modeling-friendly transformation)

This two-stage approach ensures both peak awareness and model stability.

---

### 🧠 Step 3: Feature Engineering

#### 3.1 Time-Based Features

**Temporal components:**
* Hour of day (0-23)
* 15-minute bucket within hour (0-3)
* Day of week (0-6)
* Weekend flag (binary)

**Cyclical encoding** (to capture periodicity):
* `sin(hour)`, `cos(hour)`
* `sin(day_of_week)`, `cos(day_of_week)`

#### 3.2 CPU Daily Baseline Profile (Critical Design)

**Purpose:** Capture deterministic daily behavior patterns

**Implementation:**
* For each VM:
  * Computes **median CPU usage** per `(hour, 15-min bucket)` combination
  * Creates a 96-point daily profile (24 hours × 4 intervals)
  * Represents stable, expected behavior

**Usage in modeling:**
* Target becomes: `cpu_used − cpu_daily_profile` (residuals)
* Allows ML model to focus on **deviations from normal**, not absolute levels
* Improves model generalization across VMs

#### 3.3 CPU Lag & Rolling Features

**Lag features** (recent history):
* **Short-term lags:** 1, 2, 4, 8, 16 steps (15-min intervals)
* **Daily lag:** 96 steps (24 hours ago)
* **Weekly lag:** 672 steps (7 days ago)

**Rolling statistics:**
* **Mean:**
  * Short window: Last 8 steps (2 hours)
  * Long window: Last 96 steps (24 hours)
* **Max:**
  * Short window: Last 8 steps
  * Long window: Last 96 steps

**Volatility indicators:**
* 24-hour standard deviation
* 95th percentile over last 96 steps
* Active ratio (% of time usage > 10%)
* Spike detection flag

**⚠️ Important:** VMs without sufficient history for lag features are automatically excluded from training.

#### 3.4 Memory Features

* Same time-based features as CPU
* Lag features and rolling statistics
* **No spike modeling** (memory is inherently stable)
* Simpler feature set compared to CPU

---

### 🤖 Step 4: Model Training

#### 4.1 CPU Forecasting Model

**Model Architecture:**
* **Algorithm:** LightGBM (Gradient Boosting)
* **Type:** Global model (trained across all VMs)
* **Target variable:**
```
  cpu_residual = cpu_used − cpu_daily_profile
```

**Training Strategy:**
* **Loss function:** Huber loss (robust to outliers/spikes)
* **Train/validation split:** Time-based (80% / 20%)
* **Weighting:** Spike-aware sample weights
* **Features:** Lag, rolling, temporal, profile baseline

**Model Benefits:**
* Captures non-linear patterns
* Handles cross-VM learning
* Robust to data anomalies
* Fast inference for 1000+ VMs

#### 4.2 Memory Forecasting Model

**Model Type:** Deterministic baseline

**Strategy:**
* **Lag-1 carry-forward** (last observed value)
* No ML training required

**Rationale:**
* Memory usage is highly stable
* Low variance across time
* Minimal benefit from complex modeling
* Reduces computational overhead

---

### 📊 Step 5: Model Evaluation

#### Evaluation Metrics

* **MAE (Mean Absolute Error)** – Average prediction error
* **RMSE (Root Mean Squared Error)** – Penalizes large errors

#### Comparison Baselines

* **CPU:** Baseline vs LightGBM performance
* **Per-VM improvement:** Tracked individually
* **Aggregate improvement:** Overall system-level gains

#### Evaluation Outputs

* Metrics logged to:
  * `data/training_metadata.csv`
  * `data/metrics_history/`
* Per-VM validation results
* Model performance summary

---

### 🔮 Step 6: Forecast Generation

#### Forecast Specifications

* **Resolution:** 15 minutes
* **Horizon:** 15 days
* **Total steps:** 15 days × 96 intervals/day = **1,440 forecast points**

#### 6.1 CPU Forecasting

**Method:** Recursive multi-step forecasting

**Process:**
1. Start with last observed features
2. Predict next 15-min interval
3. Update lag queue with prediction
4. Update rolling features
5. Incorporate daily profile for that hour
6. Repeat for 1,440 steps

**Safety mechanisms:**
* Predictions clipped to reasonable bounds (based on p95)
* Rolling volatility features prevent runaway forecasts
* Daily profile anchors predictions to normal patterns

#### 6.2 Memory Forecasting

**Method:** Deterministic forward projection

**Process:**
* Carry forward last observed memory value
* Applied uniformly across forecast horizon
* Simple, stable, and reliable

---

### 📦 Step 7: Write Outputs to MinIO

#### 7.1 Forecast Outputs

**Location:**
```
influxdb/monitoring-data/forecasted-data/
├── cpu_forecast_<run_date>.parquet
└── memory_forecast_<run_date>.parquet
```

**Schema:**

| Column | Type | Description |
|--------|------|-------------|
| `vm_uuid` | string | VM identifier |
| `timestamp` | datetime | Forecast timestamp (UTC) |
| `cpu_used_forecast` | float | Predicted CPU value |
| `memory_used_forecast` | float | Predicted memory value |
| `horizon_minutes` | int | Minutes ahead from run time |
| `model_name` | string | Model identifier |
| `run_date` | date | Forecast generation date |

#### 7.2 Model Artifacts

**Saved models:**
```
models/
├── cpu_forecasting_model_<run_date>.pkl
└── feature_config_<run_date>.json
```

#### 7.3 Metadata & Audit Trail

**Training metadata:**
```
data/training_metadata.csv
```

**Contents:**
* Training duration
* VM counts:
  * Total VMs processed
  * VMs successfully trained
  * VMs dropped (with reasons)
* Data windows used
* Model path
* Status & remarks

**Metrics history:**
```
data/metrics_history/
├── training_metrics_<run_date>.json
└── validation_results_<run_date>.csv
```

---

## 📁 Project Structure
```
ml_forecasting_pipeline/
│
├── run_pipeline.py               # Pipeline entrypoint
├── README.md                     # This documentation
├── requirements.txt              # Python dependencies
│
├── logs/                         # Runtime logs
│   └── pipeline_YYYY-MM-DD.log
│
├── data/
│   ├── training_metadata.csv    # Training audit trail
│   └── metrics_history/         # Model performance logs
│
├── models/                       # Saved model artifacts
│   ├── cpu_forecasting_model_*.pkl
│   └── feature_config_*.json
│
├── config/
│   ├── minio.yaml               # MinIO connection config
│   └── pipeline_config.yaml     # Pipeline parameters
│
└── src/
    ├── __init__.py
    ├── logger.py                # Centralized logging
    ├── data_loader.py           # Load data from MinIO
    ├── preprocessor.py          # Gap filling, validation
    ├── aggregator.py            # 1-min → 15-min aggregation
    ├── feature_engineer.py      # Feature generation
    ├── model_trainer.py         # LightGBM training
    ├── forecaster.py            # Recursive forecasting
    ├── evaluator.py             # Model evaluation
    └── minio_writer.py          # Write outputs to MinIO
```

---

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

### `config/pipeline_config.yaml`
```yaml
preprocessing:
  gap_fill_rules:
    small_gap_minutes: 5
    medium_gap_minutes: 30
    large_gap_minutes: 120
    max_gap_hours: 24
  
aggregation:
  target_frequency: 15min
  method: mean

feature_engineering:
  lag_steps: [1, 2, 4, 8, 16, 96, 672]
  rolling_windows: [8, 96]
  
model:
  algorithm: lightgbm
  loss: huber
  train_split: 0.8
  
forecast:
  horizon_days: 15
  resolution_minutes: 15
```

---

## 🚀 How to Run

### 1️⃣ Create Virtual Environment
```bash
python -m venv ml_pipeline_venv
source ml_pipeline_venv/bin/activate  # On Windows: ml_pipeline_venv\Scripts\activate
```

### 2️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install pandas numpy scikit-learn lightgbm minio pyarrow pyyaml
```

### 3️⃣ Run Pipeline
```bash
python run_pipeline.py
```

### 4️⃣ Monitor Logs
```bash
tail -f logs/pipeline_$(date +%Y-%m-%d).log
```

---

## 📊 Logging & Observability

### Log Categories

* **Pipeline lifecycle:** Start, completion, duration
* **Data loading:** VM counts, date ranges, data volume
* **Preprocessing:** Gap statistics, VM drops, fill strategies
* **Aggregation:** Pre/post aggregation row counts
* **Feature engineering:** Feature generation progress
* **Model training:** Training progress, convergence, metrics
* **Forecasting:** Forecast generation per VM
* **MinIO operations:** Write confirmations, file paths
* **Error handling:** Stack traces, failure points

### Log Levels

* **INFO** – Normal pipeline operations
* **WARNING** – Data quality issues, VM drops
* **ERROR** – Critical failures, model errors
* **DEBUG** – Detailed processing information

### Output Logs
```
logs/pipeline_YYYY-MM-DD.log
```

---

## 🔁 Key Design Principles

### 1. Decoupled from Ingestion

* **Pipeline 1** handles InfluxDB interaction
* **Pipeline 2** operates purely on MinIO data
* Clear separation of concerns

### 2. Peak-Safe Ingestion, Smooth Modeling

* **Pipeline 1:** MAX aggregation preserves spikes
* **Pipeline 2:** MEAN aggregation enables stable modeling
* Two-stage approach balances safety and predictability

### 3. Auditable & Reproducible

* All outputs timestamped
* Metadata tracked for every run
* Model artifacts versioned
* Complete audit trail maintained

### 4. Scalable to Thousands of VMs

* Global modeling approach
* Efficient batch processing
* Memory-optimized operations
* Parallel-ready architecture

### 5. Production-Ready

* Comprehensive error handling
* Graceful degradation (VM drops)
* Detailed logging
* State persistence

---

## ✅ Key Benefits

* **Robust data quality** – Multi-strategy gap filling
* **Feature-rich modeling** – Captures seasonality, trends, spikes
* **Production-grade ML** – LightGBM with robust loss
* **Long-horizon forecasts** – 15-day ahead predictions
* **Scalable architecture** – Handles 10,000+ VMs
* **Fully decoupled** – No InfluxDB dependency
* **Audit-ready** – Complete metadata tracking

---

## 🔗 Pipeline Dependencies

### Input from:

* **Pipeline 1** – Raw 1-minute VM metrics in MinIO

### Outputs to:

* **Pipeline 3** – Forecasts written to MinIO for InfluxDB sync
* **MinIO** – Forecast parquet files, model artifacts, metadata

---

## 📌 Future Enhancements

* **Multi-model ensemble** – Combine LightGBM, Prophet, LSTM
* **Hyperparameter tuning** – Automated HPO with Optuna
* **Anomaly detection** – Flag unusual patterns during forecasting
* **Confidence intervals** – Probabilistic forecasts
* **Online learning** – Incremental model updates
* **Feature importance tracking** – Monitor feature drift
* **A/B testing framework** – Compare model versions
* **GPU acceleration** – Faster training for large datasets
* **Distributed training** – Multi-node LightGBM
* **Real-time inference** – Stream processing mode

---

## 🧠 Summary

Pipeline 2 transforms raw VM monitoring data into actionable 15-day forecasts through a sophisticated ML workflow. It ensures data quality through intelligent gap handling, captures complex temporal patterns through rich feature engineering, trains robust models that generalize across thousands of VMs, and generates reliable long-horizon forecasts. The pipeline's decoupled architecture, comprehensive logging, and metadata tracking make it production-ready and audit-compliant.

---

**Pipeline Sequence:**
1. **Pipeline 1** – InfluxDB → MinIO (Data Ingestion)
2. **Pipeline 2** – ML Processing & Forecasting ← *You are here*
3. **Pipeline 3** – MinIO → InfluxDB (Forecast Sync)