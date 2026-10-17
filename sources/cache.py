"""Local TTL cache in .cache/ (gitignored).

It exists for speed only: every value still comes from a live API call, just not more often than the
TTL in config.yaml. One function: cached(key, ttl_seconds, fetch) -> bytes.
"""

import time
from collections.abc import Callable

from config import CONFIG, ROOT

CACHE_DIR = ROOT / CONFIG["cache"]["dir"]


def cached(key: str, ttl_seconds: int, fetch: Callable[[], bytes]) -> bytes:
    """Return the cached bytes for `key` if younger than `ttl_seconds`, else call `fetch` and store."""
    path = CACHE_DIR / key
    if path.exists() and time.time() - path.stat().st_mtime < ttl_seconds:
        return path.read_bytes()
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def ttl(source: str) -> int:
    return CONFIG["cache"]["ttl_seconds"][source]
