"""Pure metric functions: plain inputs in, numbers out. No network, no scoring, no thresholds.

Every metric here has a unit test with a hand-computed fixture (tests/test_metrics.py).
Percentiles, weights and labels live in scoring.py.
"""

import math

import pandas as pd

# --- Time windows (one rule everywhere) ----------------------------------------------------------


def latest_12_window(latest_month: str) -> tuple[str, str]:
    """Latest 12 published months, rolling. '2026-04' -> ('2025-05', '2026-04')."""
    end = pd.Period(latest_month, "M")
    return str(end - 11), str(end)


def years_between(start_year_end: str, window_end: str) -> float:
    """Years between the end of a calendar-year window and the end of the latest window.

    '2022-12' -> '2026-04' = 40 months = 3.333 years. Both windows are 12 months long, so their
    midpoints are the same distance apart.
    """
    return ((pd.Period(window_end, "M") - pd.Period(start_year_end, "M")).n) / 12


# --- Totals per airport --------------------------------------------------------------------------


def totals(monthly: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Sum departures, passengers, seats per airport over months start..end; count months present."""
    m = monthly[(monthly["month"] >= start) & (monthly["month"] <= end)]
    out = m.groupby("airport")[["departures", "passengers", "seats"]].sum()
    out["months"] = m.groupby("airport")["month"].nunique()
    return out


# --- Ratios (each one line, each one meaning) ----------------------------------------------------


def ratio(a, b):
    """a / b, with NaN when b is 0 or missing. Works on numbers and pandas Series."""
    if isinstance(b, pd.Series):
        return a / b.where(b != 0)
    return a / b if b else float("nan")


def load_factor(passengers, seats):
    """Share of seats filled."""
    return ratio(passengers, seats)


def growth(now, base):
    """% change: now vs base. 0.10 = +10%."""
    return ratio(now, base) - 1


def cagr(now, base, years: float):
    """Compound annual growth rate from base to now over `years`."""
    return ratio(now, base) ** (1 / years) - 1


def seats_per_departure(seats, departures):
    return ratio(seats, departures)


def upgauging(seats_now, dep_now, seats_base, dep_base):
    """% change in seats per departure, now vs base. Airlines flying bigger planes -> positive."""
    return growth(seats_per_departure(seats_now, dep_now), seats_per_departure(seats_base, dep_base))


def departures_per_runway(departures, runways):
    """Annual departures per effective runway (A-15). NaN when no effective runway."""
    return ratio(departures, runways)


def seasonality_ratio(monthly: pd.DataFrame, start: str, end: str) -> pd.Series:
    """Busiest month / quietest month of passengers per airport over start..end (A-18)."""
    m = monthly[(monthly["month"] >= start) & (monthly["month"] <= end)]
    g = m.groupby("airport")["passengers"]
    return ratio(g.max(), g.min())


def nas_share(delays: pd.DataFrame) -> pd.Series:
    """NAS (runway/ATC) delay minutes / all arrival delay minutes, per airport."""
    g = delays.groupby("airport")[["nas_delay", "arr_delay"]].sum()
    return ratio(g["nas_delay"], g["arr_delay"])


def freighter_share(segments: pd.DataFrame) -> pd.Series:
    """Freighter departures / all departures per origin airport (TranStats aircraft config)."""
    dep = segments.groupby(["ORIGIN", "aircraft"])["DEPARTURES_PERFORMED"].sum().unstack(fill_value=0)
    return ratio(dep.get("freighter", 0), dep.sum(axis=1))


# --- Peer group (A-02, A-03) ---------------------------------------------------------------------

HUB_CLASSES = ["large", "medium", "small"]  # order matters: first cutoff met wins; below all -> non-hub


def hub_class(share: float, cutoffs: dict) -> str:
    """FAA hub class from share of national enplanements: large >= 1%, medium >= 0.25%, small >= 0.05%."""
    for c in HUB_CLASSES:
        if share >= cutoffs[c]:
            return c
    return "non-hub"


def is_borderline(share: float, cutoffs: dict, margin: float) -> bool:
    """True when the share is within +/- margin (relative) of any hub cutoff (A-02 'borderline class' note)."""
    return any(abs(share - cutoffs[c]) <= margin * cutoffs[c] for c in HUB_CLASSES)


# --- Route mix (Q3) ------------------------------------------------------------------------------


def great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in km (Earth radius 6,371 km)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def long_haul_share(distance_km: pd.Series, flights: pd.Series, threshold_km: float) -> float:
    """Share of flights (weighted by departures) longer than threshold_km."""
    total = flights.sum()
    return float(flights[distance_km > threshold_km].sum() / total) if total else float("nan")


DISTANCE_BUCKETS_KM = [0, 1500, 4000, 8000, float("inf")]
BUCKET_LABELS = ["< 1,500 km", "1,500-4,000 km", "4,000-8,000 km", "> 8,000 km"]


def distance_buckets(distance_km: pd.Series, flights: pd.Series) -> dict:
    """Departures per distance bucket (bucket edges are display bands; long-haul uses A-05)."""
    b = pd.cut(distance_km, DISTANCE_BUCKETS_KM, labels=BUCKET_LABELS, right=False)
    return flights.groupby(b, observed=False).sum().astype(int).to_dict()


# --- Airfield capacity (A-10) --------------------------------------------------------------------


def capacity_loss_per_hour(reference_rate: float, current_rate: float) -> tuple[float, float]:
    """Arrivals per hour lost, and as a share of the reference rate. (54, 40) -> (14, 0.259)."""
    lost = reference_rate - current_rate
    return lost, lost / reference_rate
