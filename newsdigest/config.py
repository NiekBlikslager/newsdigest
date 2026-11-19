"""Loads the files in config/ so the rest of the code can stay simple."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
STATE_FILE = ROOT / "state" / "state.json"
OUTPUT_DIR = ROOT / "output"


def load_settings() -> dict:
    with open(CONFIG_DIR / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources() -> list[dict]:
    with open(CONFIG_DIR / "sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def load_profile() -> str:
    return (CONFIG_DIR / "profile.md").read_text(encoding="utf-8")
