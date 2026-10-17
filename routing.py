"""Deterministic period -> data source routing (principle 3: the LLM never picks the source).

Accepted periods (the agent passes one of these strings):
  "last_7_days"            -> OpenSky (all flights, no passenger/cargo split)
  "latest"                 -> TranStats, the SAME 12 months as the score (A-26)
  "2025"                   -> TranStats, that calendar year
  "2025-Q3"                -> TranStats, that quarter
  "2025-07"                -> TranStats, that month
Anything else (e.g. a specific day "2024-03-03") is unsupported; we say so and offer the nearest
supported period.
"""

import re
from dataclasses import dataclass, field

import pandas as pd

import metrics
from sources import bts


@dataclass
class Route:
    source: str                                   # "opensky" | "transtats" | "unsupported"
    months: list[str] = field(default_factory=list)   # "YYYY-MM", for TranStats
    label: str = ""                               # human-readable window, stated in every answer
    message: str = ""                             # for unsupported periods: why, and the nearest supported period


def _months(start: str, end: str) -> list[str]:
    return [str(p) for p in pd.period_range(start, end, freq="M")]


def route(period: str) -> Route:
    period = period.strip()
    if period == "last_7_days":
        return Route("opensky", label="last 7 days")

    latest = bts.transtats_latest()                     # e.g. "2026-07"
    if period == "latest":
        start, end = metrics.latest_12_window(bts.latest_month())   # same window as the score (A-26)
        return Route("transtats", _months(start, end), f"{start} to {end}")

    if m := re.fullmatch(r"(\d{4})", period):
        months = _months(f"{m[1]}-01", f"{m[1]}-12")
        return _check(Route("transtats", months, f"calendar {m[1]}"), period, latest)

    if m := re.fullmatch(r"(\d{4})-Q([1-4])", period):
        q = int(m[2])
        months = _months(f"{m[1]}-{3 * q - 2:02d}", f"{m[1]}-{3 * q:02d}")
        return _check(Route("transtats", months, f"{m[1]} Q{q}"), period, latest)

    if m := re.fullmatch(r"(\d{4})-(\d{2})", period):
        return _check(Route("transtats", [period], period), period, latest)

    if m := re.fullmatch(r"(\d{4})-(\d{2})-\d{2}", period):
        return Route("unsupported", message=(
            f"Single days aren't supported: T-100 is monthly. Nearest supported period: {m[1]}-{m[2]} "
            f"(that month), or 'last_7_days' if the day is within the past week."))

    return Route("unsupported", message=(
        "Unsupported period. Use 'last_7_days', 'latest', a year (2025), a quarter (2025-Q3) or a month (2025-07)."))


def _check(r: Route, period: str, latest: str) -> Route:
    """Refuse periods that end after the latest published month."""
    if r.months[-1] > latest:
        return Route("unsupported", message=(
            f"{period} isn't published yet: TranStats T-100 runs through {latest}. "
            f"Nearest supported period: {latest} (latest month) or 'latest' (the latest 12 months)."))
    return r
