from datetime import datetime, timezone
import sys
import time

from src.logger import get_logger
from src.minio_reader import (
    load_minio_config,
    get_minio_client,
    read_cpu_forecast,
    read_memory_forecast
)
from src.schema_mapper import (
    map_cpu_forecast,
    map_memory_forecast
)
from src.influx_writer import (
    get_influx_writer,
    write_forecast_df
)
from src.state_manager import (
    is_run_date_synced,
    mark_run_date_synced
)
from src.validators import validate_before_influx_write
from src.delete_old_forecasts import delete_old_forecasts


# ============================================================
# LOGGER
# ============================================================
logger = get_logger("forecast_sync")

# ============================================================
# CONFIG
# ============================================================
RUN_DATE = datetime.now(timezone.utc).date().isoformat()


# ============================================================
# MAIN
# ============================================================
def main():
    pipeline_start = time.perf_counter()
    pipeline_start_ts = datetime.now(timezone.utc)

    logger.info(
        f"PIPELINE_START | run_date={RUN_DATE} | "
        f"ts={pipeline_start_ts.isoformat()} | timezone=UTC"
    )

    # --------------------------------------------------------
    # ONE-TIME TIMESTAMP STANDARD (VERY IMPORTANT)
    # --------------------------------------------------------
    logger.info(
        "TIMESTAMP_STANDARD | "
        "source=minio_parquet | "
        "stored_dtype=datetime64[ns, UTC] | "
        "timezone=UTC | "
        "timestamp_value_changed=false"
    )

    # --------------------------------------------------------
    # STATE CHECK
    # --------------------------------------------------------
    if is_run_date_synced(RUN_DATE):
        logger.info("STATE_CHECK | already_synced=true | exiting")
        return

    # --------------------------------------------------------
    # INIT CLIENTS
    # --------------------------------------------------------
    logger.info("INIT_CLIENTS | starting")

    # ---- MinIO ----
    minio_cfg = load_minio_config()
    minio_client = get_minio_client(minio_cfg)

    # ---- InfluxDB ----
    write_api, influx_client, influx_cfg = get_influx_writer()

    try:
        # ----------------------------------------------------
        # READ FORECASTS FROM MINIO
        # ----------------------------------------------------
        read_start = time.perf_counter()

        df_cpu_raw = read_cpu_forecast(
            client=minio_client,
            bucket=minio_cfg["bucket"],
            prefix=minio_cfg["prefix"],
            run_date=RUN_DATE
        )

        df_mem_raw = read_memory_forecast(
            client=minio_client,
            bucket=minio_cfg["bucket"],
            prefix=minio_cfg["prefix"],
            run_date=RUN_DATE
        )

        logger.info(
            "MINIO_READ | "
            f"cpu_rows={0 if df_cpu_raw is None else len(df_cpu_raw)} | "
            f"memory_rows={0 if df_mem_raw is None else len(df_mem_raw)} | "
            f"duration_seconds={time.perf_counter() - read_start:.2f}"
        )

        if (df_cpu_raw is None or df_cpu_raw.empty) and (
            df_mem_raw is None or df_mem_raw.empty
        ):
            logger.warning("NO_FORECAST_DATA | exiting")
            return

        # ----------------------------------------------------
        # MAP SCHEMA
        # ----------------------------------------------------
        logger.info(
            "SCHEMA_MAPPING | "
            "action=rename_cast_columns | "
            "timestamp_dtype_preserved=datetime64[ns, UTC]"
        )

        df_cpu = map_cpu_forecast(df_cpu_raw) if df_cpu_raw is not None and not df_cpu_raw.empty else None
        df_mem = map_memory_forecast(df_mem_raw) if df_mem_raw is not None and not df_mem_raw.empty else None

        # ----------------------------------------------------
        # WRITE CPU FORECAST
        # ----------------------------------------------------
        if df_cpu is not None:
            logger.info(
                "INFLUX_WRITE_START | measurement=cpu_usage | "
                "timestamp_format=RFC3339 | timezone=UTC"
            )

            validate_before_influx_write(
                df=df_cpu,
                forecast_field="cpu_used_forecast",
                run_date=RUN_DATE
            )

            write_forecast_df(
                write_api=write_api,
                cfg=influx_cfg,
                measurement="cpu_usage",
                df=df_cpu,
                forecast_field="cpu_used_forecast",
                convert_to_ist=True
            )

            logger.info(
                f"INFLUX_WRITE_END | measurement=cpu_usage | rows={len(df_cpu)}"
            )

        # ----------------------------------------------------
        # WRITE MEMORY FORECAST
        # ----------------------------------------------------
        if df_mem is not None:
            logger.info(
                "INFLUX_WRITE_START | measurement=memory_usage | "
                "timestamp_format=RFC3339 | timezone=UTC"
            )

            validate_before_influx_write(
                df=df_mem,
                forecast_field="memory_used_forecast",
                run_date=RUN_DATE
            )

            write_forecast_df(
                write_api=write_api,
                cfg=influx_cfg,
                measurement="memory_usage",
                df=df_mem,
                forecast_field="memory_used_forecast",
                convert_to_ist=True
            )

            logger.info(
                f"INFLUX_WRITE_END | measurement=memory_usage | rows={len(df_mem)}"
            )

        # ----------------------------------------------------
        # MARK STATE
        # ----------------------------------------------------
        mark_run_date_synced(
            RUN_DATE,
            notes="Forecast successfully written to InfluxDB"
        )

        # ----------------------------------------------------
        # FORECAST RETENTION CLEANUP
        # ----------------------------------------------------
        logger.info("RETENTION_CLEANUP | retention_days=7")
        delete_old_forecasts(retention_days=7)

        logger.info(
            f"PIPELINE_SUCCESS | "
            f"total_duration_seconds={time.perf_counter() - pipeline_start:.2f} | "
            f"timezone=UTC"
        )

    finally:
        # ----------------------------------------------------
        # CLEAN SHUTDOWN
        # ----------------------------------------------------
        logger.info("INFLUX_CLIENT_CLOSE")
        influx_client.close()


# ============================================================
# ENTRYPOINT
# ============================================================
if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("PIPELINE_FAILED")
        sys.exit(1)
