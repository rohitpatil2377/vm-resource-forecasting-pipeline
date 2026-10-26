# src/utils.py

import yaml
import os


def load_yaml(path: str) -> dict:
    """
    Load a YAML configuration file safely.

    Args:
        path (str): Path to YAML file

    Returns:
        dict: Parsed YAML content

    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If YAML is empty or invalid
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"YAML config file not found: {path}")

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(f"YAML file is empty or invalid: {path}")

    return data
