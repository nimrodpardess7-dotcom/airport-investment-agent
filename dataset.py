"""Builds the airport table: one row per U.S. airport, every metric the score and label need.

This is the only place that joins sources and metrics. scoring.py receives this table and never
fetches anything, so it can be tested on a hand-made table.
"""

import pandas as pd

import metrics as m
from config import CONFIG
from sources import bts, ourairports


def build() -> tuple[pd.DataFrame, dict]:
    """Return (table, meta). meta holds the data windows every answer must state."""
    latest = bts.latest_month()
    start, end = m.latest_12_window(latest)
    base, mom = CONFIG["scoring"]["windows"]["baseline_year"], CONFIG["scoring"]["windows"]["cagr_start_year"]

    monthly_now = bts.monthly(start, end)
    now = m.totals(monthly_now, start, end)
    b19 = m.totals(bts.monthly(f"{base}-01", f"{base}-12"), f"{base}-01", f"{base}-12")
    b22 = m.totals(bts.monthly(f"{mom}-01", f"{mom}-12"), f"{mom}-01", f"{mom}-12")

    # Universe (A-03): U.S. airports with more than the minimum enplanements in the latest 12 months.
    us = ourairports.airports()
    now = now[now.index.isin(us.index) & (now["passengers"] > CONFIG["universe_min_enplanements"])]
    b19, b22 = b19.reindex(now.index), b22.reindex(now.index)

    t = pd.DataFrame(index=now.index)
    t["name"], t["state"], t["runways"] = us["name"], us["state"], us["runways"]
    t["passengers"] = now["passengers"]
    t["departures"] = now["departures"]
    # A-19: worst gap across the three 12-month windows (an airport absent in 2019 is missing 12).
    t["missing_months"] = pd.concat([12 - w["months"].fillna(0) for w in (now, b19, b22)], axis=1).max(axis=1)
    t["growth_vs_2019"] = m.growth(now["passengers"], b19["passengers"])
    t["cagr_since_2022"] = m.cagr(now["passengers"], b22["passengers"], m.years_between(f"{mom}-12", end))
    t["load_factor"] = m.load_factor(now["passengers"], now["seats"])
    t["upgauging"] = m.upgauging(now["seats"], now["departures"], b19["seats"], b19["departures"])
    t["departures_change"] = m.growth(now["departures"], b19["departures"])
    t["departures_per_runway"] = m.departures_per_runway(now["departures"], t["runways"])
    t["seasonality"] = m.seasonality_ratio(monthly_now, start, end)

    # Airfield evidence: NAS delay share (reporting airlines only, latest 12 months available).
    delays = bts.delay_causes()
    t["nas_share"] = m.nas_share(delays).reindex(t.index)

    # Cargo-heavy flag (A-20): freighter share from TranStats, latest full calendar year.
    ts_latest = bts.transtats_latest()
    full_year = int(ts_latest[:4]) if ts_latest.endswith("-12") else int(ts_latest[:4]) - 1
    t["freighter_share"] = m.freighter_share(bts.segments(full_year)).reindex(t.index)

    # Peer group (A-02): share of national enplanements within the universe.
    cutoffs = CONFIG["peer_groups"]
    t["national_share"] = t["passengers"] / t["passengers"].sum()
    t["hub_class"] = t["national_share"].map(lambda s: m.hub_class(s, cutoffs))
    t["borderline_class"] = t["national_share"].map(lambda s: m.is_borderline(s, cutoffs, cutoffs["borderline_margin"]))

    meta = {
        "score_window": f"T-100 summary, {start} to {end} (vs {base} and {mom})",
        "nas_window": f"TranStats delay causes, {delays['month'].min()} to {delays['month'].max()} (reporting airlines only)",
        "freighter_window": f"TranStats T-100 segments, calendar {full_year}",
        "airports_in_universe": len(t),
        # Plain fields for display (app sidebar).
        "score_period": (start, end),
        "nas_period": (delays["month"].min(), delays["month"].max()),
        "freighter_year": full_year,
    }
    return t, meta
