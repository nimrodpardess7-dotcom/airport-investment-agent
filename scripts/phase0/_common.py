"""Shared helpers for Phase 0 probe scripts: timing, output folder, result dump."""

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".cache" / "phase0"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "airport-investment-agent phase0 probe"}


class Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.seconds = round(time.perf_counter() - self.t0, 2)


def save(name: str, result: dict) -> None:
    """Write the probe result to .cache/phase0/<name>.json and print it."""
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    print(f"\nsaved -> {path.relative_to(ROOT)}")
