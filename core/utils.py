"""Shared utilities for Web Contractor."""

import json
from pathlib import Path
from typing import Dict


def load_json_config(filename: str) -> Dict:
    """Load JSON config file from config directory."""
    config_path = Path(__file__).parent.parent / "config" / filename
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
