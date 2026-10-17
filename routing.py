"""Deterministic period -> data source routing (principle 3: the LLM never picks the source).

Accepted periods (the agent passes one of these strings):
  "last_7_days"            -> OpenSky (all flights, no passenger/cargo split)
  "latest"                 -> TranStats, latest full calendar year
  "2025"                   -> TranStats, that calendar year
  "2025-Q3"                -> TranStats, that quarter
  "2025-07"                -> TranStats, that month
Anything else (e.g. a specific day "2024-03-03") is unsupported; we say so and offer the nearest
supported period.
"""

import re
from dataclasses import dataclass

from sources import bts


@dataclass
class Route:
    source: str               # "opensky" | "transtats" | "unsupported"
    year: int | None = None
    months: list[int] | None = None   # None = whole year
    label: str = ""           # human-readable window, stated in every answer
    message: str = ""         # for unsupported periods: why, and the nearest supported period


def route(period: str) -> Route:
    period = period.strip()
    if period == "last_7_days":
        return Route("opensky", label="last 7 days")

    latest = bts.transtats_latest()                     # e.g. "2026-07"
    latest_year, latest_month = int(latest[:4]), int(latest[5:])
    if period == "latest":
        year = latest_year if latest_month == 12 else latest_year - 1
        return Route("transtats", year, None, f"calendar {year}")

    if m := re.fullmatch(r"(\d{4})", period):
        year = int(m[1])
        if year > latest_year or (year == latest_year and latest_month < 12):
            return _too_new(period, latest)
        return Route("transtats", year, None, f"calendar {year}")

    if m := re.fullmatch(r"(\d{4})-Q([1-4])", period):
        year, q = int(m[1]), int(m[2])
        months = [3 * q - 2, 3 * q - 1, 3 * q]
        if (year, months[-1]) > (latest_year, latest_month):
            return _too_new(period, latest)
        return Route("transtats", year, months, f"{year} Q{q}")

    if m := re.fullmatch(r"(\d{4})-(\d{2})", period):
        year, month = int(m[1]), int(m[2])
        if (year, month) > (latest_year, latest_month):
            return _too_new(period, latest)
        return Route("transtats", year, [month], f"{year}-{month:02d}")

    if m := re.fullmatch(r"(\d{4})-(\d{2})-\d{2}", period):
        return Route("unsupported", message=(
            f"Single days aren't supported: T-100 is monthly. Nearest supported period: {m[1]}-{m[2]} "
            f"(that month), or 'last_7_days' if the day is within the past week."))

    return Route("unsupported", message=(
        "Unsupported period. Use 'last_7_days', 'latest', a year (2025), a quarter (2025-Q3) or a month (2025-07)."))


def _too_new(period: str, latest: str) -> Route:
    return Route("unsupported", message=(
        f"{period} isn't published yet: TranStats T-100 runs through {latest}. "
        f"Nearest supported period: {latest} (latest month) or 'latest' (latest full year)."))
