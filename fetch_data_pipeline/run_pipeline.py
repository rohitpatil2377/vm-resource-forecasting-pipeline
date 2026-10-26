# src/run_pipeline.py

from datetime import datetime, timedelta, UTC
import sys
import traceback
import subprocess
import pandas as pd
from pathlib import Path

from src.fetch_data import (
    load_influx,
    load_vm_list,
    get_query_api,
    vm_has_min_history,
    fetch_day_data
)

from src.minio_utils import (
    get_minio_client,
    list_minio_days,
    write_parquet_to_minio,
    delete_minio_prefix,
    read_parquet_from_minio,
    get_existing_vms_for_day
)

from src.build_processed_data import build_processed_dataset


# ============================================================
# PATHS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
COLLECTOR_SCRIPT = BASE_DIR / "src" / "vm_uuid_collector.py"

# ============================================================
# CONFIG (SOURCE OF TRUTH)
# ============================================================
RAW_PREFIX = "influxdb/monitoring-data/raw-data"
PROCESSED_PREFIX = "influxdb/monitoring-data/processed-data"
PROCESSED_FILE = f"{PROCESSED_PREFIX}/vm_timeseries.parquet"

MIN_HISTORY_DAYS = 20     # ✅ forecast eligibility
MAX_WINDOW_DAYS = 25     # ✅ retention + training window


# ============================================================
# RUN VM UUID COLLECTOR
# ============================================================
def run_vm_uuid_collector():
    print("\n" + "=" * 80)
    print("🔁 RUNNING VM UUID COLLECTOR")
    print("=" * 80)

    if not COLLECTOR_SCRIPT.exists():
        raise RuntimeError(f"Collector not found: {COLLECTOR_SCRIPT}")

    result = subprocess.run(
        [sys.executable, str(COLLECTOR_SCRIPT)],
        capture_output=True,
        text=True
    )

    print(result.stdout)

    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError("VM UUID Collector failed")

    print("✅ VM UUID COLLECTOR COMPLETED SUCCESSFULLY")


# ============================================================
# MAIN PIPELINE
# ============================================================
def main():
    try:
        print("\n" + "=" * 80)
        print("🚀 VM MONITORING INGESTION PIPELINE STARTED")
        print("=" * 80)

        # --------------------------------------------------
        # STEP 1: COLLECT VM SNAPSHOT
        # --------------------------------------------------
        run_vm_uuid_collector()

        # --------------------------------------------------
        # STEP 2: LOAD VM LIST
        # --------------------------------------------------
        print("\n📋 Loading VM list...")
        vm_list = load_vm_list()

        if not vm_list:
            print("⚠️ No VMs received today. Exiting gracefully.")
            sys.exit(0)

        print(f"🔢 TOTAL VMs PROVIDED: {len(vm_list)}")

        # --------------------------------------------------
        # STEP 3: LOAD CONFIGS & CLIENTS
        # --------------------------------------------------
        influx_cfg = load_influx()
        query_api = get_query_api(influx_cfg)

        minio, bucket = get_minio_client()
        print(f"📦 Connected to MinIO bucket: {bucket}")

        # --------------------------------------------------
        # STEP 4: VM HISTORY ELIGIBILITY CHECK
        # --------------------------------------------------
        print("\n🔍 Checking VM historical availability")
        print(f"📏 Minimum required history: {MIN_HISTORY_DAYS} days\n")

        eligible_vms = []
        dropped_vms = []

        for idx, vm in enumerate(vm_list, 1):
            print(f"[{idx:>4}/{len(vm_list)}] VM {vm} → ", end="")

            ok = vm_has_min_history(
                query_api=query_api,
                bucket=influx_cfg["bucket"],
                vm_uuid=vm,
                min_days=MIN_HISTORY_DAYS
            )

            if ok:
                eligible_vms.append(vm)
                print("✅ ELIGIBLE")
            else:
                dropped_vms.append(vm)
                print("❌ DROPPED (< 90 days)")

        if not eligible_vms:
            print("\n⚠️ No eligible VMs after history check. Exiting.")
            sys.exit(0)

        print(f"\n📊 ELIGIBLE VMs: {len(eligible_vms)}")
        print(f"❌ DROPPED VMs : {len(dropped_vms)}")

        # --------------------------------------------------
        # STEP 5: DETERMINE DATE WINDOW (180 DAYS)
        # --------------------------------------------------
        today = datetime.now(UTC).date()
        window_start = today - timedelta(days=MAX_WINDOW_DAYS - 1)

        print("\n" + "-" * 60)
        print("📅 DATA WINDOW")
        print("-" * 60)
        print(f"➡️ Window start : {window_start}")
        print(f"➡️ Window end   : {today}")

        days_to_process = [
            window_start + timedelta(days=i)
            for i in range(MAX_WINDOW_DAYS)
        ]

        # --------------------------------------------------
        # STEP 6: FETCH & STORE DAILY DATA (INCREMENTAL)
        # --------------------------------------------------
        print("\n" + "=" * 80)
        print("📥 DAILY DATA INGESTION")
        print("=" * 80)

        for idx, day in enumerate(days_to_process, 1):
            day_str = day.strftime("%Y-%m-%d")
            object_path = f"{RAW_PREFIX}/{day_str}/data.parquet"

            print(f"\n📅 [{idx}/{len(days_to_process)}] Processing {day_str}")

            existing_vms = get_existing_vms_for_day(
                minio=minio,
                bucket=bucket,
                day_object_path=object_path
            )

            missing_vms = sorted(set(eligible_vms) - existing_vms)

            if not missing_vms:
                print("✅ All eligible VMs already present — skipping")
                continue

            print(f"🔄 Fetching {len(missing_vms)} missing VMs")

            new_df = fetch_day_data(
                query_api=query_api,
                bucket=influx_cfg["bucket"],
                vms=missing_vms,
                day=day
            )

            if new_df.empty:
                print("⚠️ No data fetched")
                continue

            if existing_vms:
                old_df = read_parquet_from_minio(
                    minio=minio,
                    bucket=bucket,
                    object_path=object_path
                )

                final_df = (
                    pd.concat([old_df, new_df], ignore_index=True)
                    .drop_duplicates(
                        subset=["timestamp", "vm_uuid"],
                        keep="last"
                    )
                )
            else:
                final_df = new_df

            write_parquet_to_minio(
                minio=minio,
                bucket=bucket,
                object_path=object_path,
                df=final_df
            )

            print(f"✅ Rows written: {len(final_df):,}")

        # --------------------------------------------------
        # STEP 7: RETENTION (DELETE > 180 DAYS)
        # --------------------------------------------------
        print("\n" + "-" * 60)
        print("🧹 RETENTION POLICY")
        print("-" * 60)

        all_days = list_minio_days(minio, bucket, RAW_PREFIX)

        if len(all_days) > MAX_WINDOW_DAYS:
            delete_days = all_days[:-MAX_WINDOW_DAYS]
            for d in delete_days:
                delete_minio_prefix(minio, bucket, f"{RAW_PREFIX}/{d}")
                print(f"❌ Deleted {d}")
        else:
            print("✅ Retention OK")

        # --------------------------------------------------
        # STEP 8: BUILD PROCESSED DATASET
        # --------------------------------------------------
        print("\n" + "=" * 80)
        print("🧩 BUILDING PROCESSED DATASET")
        print("=" * 80)

        build_processed_dataset(
            minio=minio,
            bucket=bucket,
            raw_prefix=RAW_PREFIX,
            output_object=PROCESSED_FILE
        )

        print("\n" + "=" * 80)
        print("🎉 PIPELINE COMPLETED SUCCESSFULLY")
        print("=" * 80)

    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ PIPELINE FAILED")
        print("=" * 80)
        print(str(e))
        traceback.print_exc()
        sys.exit(1)


# ============================================================
# ENTRYPOINT
# ============================================================
if __name__ == "__main__":
    main()
