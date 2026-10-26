# src/utils.py

import yaml
import os
from typing import Any, Dict


# ============================================================
# LOAD YAML CONFIG
# ============================================================
def load_yaml(path: str) -> Dict[str, Any]:
    """
    Load a YAML file and return it as a dictionary.

    Fails fast if file does not exist or YAML is invalid.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"YAML config file not found: {path}")

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(f"YAML file is empty or invalid: {path}")

    return data


# ============================================================
# ENSURE DIRECTORY EXISTS (SAFE UTILITY)
# ============================================================
def ensure_dir(path: str):
    """
    Create directory if it does not exist.
    Safe to call multiple times.
    """
    os.makedirs(path, exist_ok=True)
