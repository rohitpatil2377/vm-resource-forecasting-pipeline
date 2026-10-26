# src/state_manager.py

import json
import os
from typing import Optional, List
from datetime import datetime

from src.logger import get_logger

logger = get_logger("state_manager")

# ============================================================
# STATE FILE CONFIG
# ============================================================
STATE_DIR = "data/state"
STATE_FILE = os.path.join(STATE_DIR, "forecast_sync_state.json")

os.makedirs(STATE_DIR, exist_ok=True)


# ============================================================
# LOAD STATE
# ============================================================
def _load_state() -> dict:
    """
    Loads state from disk.
    If state file does not exist, returns empty state.
    """
    if not os.path.exists(STATE_FILE):
        return {
            "last_updated": None,
            "synced_run_dates": []
        }

    with open(STATE_FILE, "r") as f:
        return json.load(f)


# ============================================================
# SAVE STATE
# ============================================================
def _save_state(state: dict):
    """
    Persists state to disk atomically.
    """
    tmp_path = STATE_FILE + ".tmp"

    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2)

    os.replace(tmp_path, STATE_FILE)


# ============================================================
# CHECK IF RUN_DATE IS ALREADY SYNCED
# ============================================================
def is_run_date_synced(run_date: str) -> bool:
    """
    Returns True if run_date has already been synced to InfluxDB.
    """
    state = _load_state()
    synced = run_date in state.get("synced_run_dates", [])

    if synced:
        logger.info(f"⏭️ run_date={run_date} already synced — skipping")

    return synced


# ============================================================
# MARK RUN_DATE AS SYNCED
# ============================================================
def mark_run_date_synced(
    run_date: str,
    notes: Optional[str] = None
):
    """
    Marks a run_date as successfully synced.
    """

    state = _load_state()

    if run_date not in state["synced_run_dates"]:
        state["synced_run_dates"].append(run_date)

    state["last_updated"] = datetime.utcnow().isoformat()

    if notes:
        state.setdefault("notes", {})
        state["notes"][run_date] = notes

    _save_state(state)

    logger.info(f"✅ Marked run_date={run_date} as synced")


# ============================================================
# GET LAST SYNCED RUN_DATE
# ============================================================
def get_last_synced_run_date() -> Optional[str]:
    """
    Returns the most recent synced run_date (or None).
    """
    state = _load_state()
    dates: List[str] = state.get("synced_run_dates", [])

    if not dates:
        return None

    # Dates are YYYY-MM-DD so lexicographic sort works
    return sorted(dates)[-1]


# ============================================================
# RESET STATE (USE WITH CAUTION)
# ============================================================
def reset_state():
    """
    Deletes all sync history.
    Useful for re-backfilling data.
    """
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        logger.warning("⚠️ Forecast sync state RESET")
    else:
        logger.info("No state file found — nothing to reset")
