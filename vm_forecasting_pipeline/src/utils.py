import yaml
import os

def load_yaml(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)

def get_env_var(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing environment variable: {key}")
    return value
