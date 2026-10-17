"""Loads config.yaml and the two KB files once. Everything changeable lives in those files."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent


def _load(name: str):
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


CONFIG = _load("config.yaml")
CONSTRAINTS = _load("kb/constraints.yaml")
ASSUMPTIONS = {a["id"]: a for a in _load("kb/assumptions.yaml")}
