"""Agent-facing tools. Plain Python: Phase 2 exposes them to the LLM unchanged.

Every tool returns the same shape:
  values       display-ready strings ("92%", "21.0M"); the LLM quotes them verbatim (grounding check)
  formula      how the numbers were computed, in words
  sources      data sources with their windows (every answer states its data window)
  assumptions  A-IDs from kb/assumptions.yaml that the answer depends on
  confidence   high | medium | low, with the reason in caveats
  caveats      what the data can't say (no silent gaps)
"""

from functools import lru_cache

import pandas as pd

import dataset
import metrics as m
import routing
import scoring
from config import ASSUMPTIONS, CONFIG, CONSTRAINTS
from sources import bts, faa, opensky, ourairports

ROUTE_CFG = CONFIG["route_mix"]


# --- Formatting: every number leaves Python as a display string ------------------------------------

def _pct(x, digits=1) -> str:
    return "n/a" if pd.isna(x) else f"{x * 100:.{digits}f}%"


def _signed(x) -> str:
    return "n/a" if pd.isna(x) else f"{x * 100:+.1f}%"


def _p(x) -> str:
    return "n/a" if pd.isna(x) else f"p{x:.0f}"


def _n(x, digits=0) -> str:
    return "n/a" if pd.isna(x) else f"{x:,.{digits}f}"


def _millions(x) -> str:
    return "n/a" if pd.isna(x) else f"{x / 1e6:.2f}M"


def _result(values, formula, sources, assumptions, confidence="high", caveats=()) -> dict:
    return {"values": values, "formula": formula, "sources": sources, "assumptions": sorted(set(assumptions)),
            "confidence": confidence, "caveats": list(caveats)}


def _error(message: str) -> dict:
    return _result({"error": message}, "", [], [], "n/a", [message])


# --- Shared data -----------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _table() -> tuple[pd.DataFrame, dict]:
    return dataset.build()


def _evaluated(weights=None, lens=None) -> pd.DataFrame:
    return scoring.evaluate(_table()[0], weights=weights, lens=lens)


def _check_code(code: str) -> str | None:
    """Return an error message for unknown or out-of-universe airports, else None."""
    code = code.upper()
    if code not in ourairports.airports().index:
        return f"Unknown U.S. airport code '{code}'. Use a 3-letter IATA code (e.g. BOS)."
    if code not in _table()[0].index:
        return f"{code} is below the scoring universe (more than 10,000 boardings in the latest 12 months, A-03)."
    return None


def _raw(row: pd.Series) -> dict:
    """The magnitudes behind the percentiles, so a reader sees "how much", not only "how it ranks"."""
    return {
        "boardings_latest_12m": _millions(row["passengers"]),
        "growth_vs_2019": f"{_signed(row['growth_vs_2019'])} ({_p(row['pct_growth_vs_2019'])})",
        "cagr_since_2022": f"{_signed(row['cagr_since_2022'])} a year ({_p(row['pct_cagr_since_2022'])})",
        "load_factor": f"{_pct(row['load_factor'])} ({_p(row['pct_load_factor'])})",
        "seats_per_departure_change_vs_2019": f"{_signed(row['upgauging'])} ({_p(row['pct_upgauging'])})",
        "departures_change_vs_2019": f"{_signed(row['departures_change'])} ({_p(row['pct_departures_change'])})",
    }


def _summary(row: pd.Series) -> dict:
    return {
        "airport": row.name, "name": row["name"], "state": row["state"], "peer_group": row["hub_class"],
        "score": _n(row["score"]), "growth": _p(row["growth"]), "pressure": _p(row["pressure"]),
        "scale": _p(row["scale"]), "raw": _raw(row),
        "label": row["label"], "label_evidence": row["label_evidence"], "near_misses": row["near_misses"],
        "flags": row["flags"], "flag_checks_not_run": row["flag_checks_not_run"],
        "projects": [f"{k['statement']} [{k['id']}]" for k in CONSTRAINTS
                     if k["airport"] == row.name and k["type"] == "project"],
    }


SCORE_FORMULA = ("score = w_growth x Growth + w_pressure x Pressure + w_scale x Scale (0-100). "
                 "Growth = mean percentile of (latest 12 months vs 2019) and (CAGR since 2022); "
                 "Pressure = mean percentile of load factor and up-gauging (seats per departure vs 2019); "
                 "Scale = percentile of passengers vs all airports. Growth/Pressure percentiles are within the "
                 "FAA hub-class peer group. Label: first match of Regulatory, Airfield, Terminal, None evident.")
SCORE_ASSUMPTIONS = ["A-01", "A-02", "A-03", "A-04", "A-11", "A-12", "A-13", "A-14", "A-16", "A-18", "A-19",
                     "A-20", "A-21", "A-22", "A-23"]
NORMALIZATION = "Each airport is compared to airports of similar size (FAA hub class); size itself is compared to all airports."


def _score_sources() -> list[str]:
    meta = _table()[1]
    return [meta["score_window"], meta["nas_window"], meta["freighter_window"], "kb/constraints.yaml"]


# --- 1. rank_airports ------------------------------------------------------------------------------

def rank_airports(region: str | None = None, states: list[str] | None = None, lens: str = "absolute",
                  weights: dict | None = None, top: int = 10) -> dict:
    """Rank airports by Opportunity Score (national percentiles, then filtered by region/states)."""
    if region:
        if region not in CONFIG["regions"]:
            return _error(f"Unknown region '{region}'. Known: {sorted(CONFIG['regions'])}, or pass states.")
        states = CONFIG["regions"][region]
    try:
        used = scoring.validate_weights(weights) if weights else scoring.lens_weights(lens)
    except ValueError as e:
        return _error(str(e))
    table, meta = _table()
    ranked = scoring.rank(table, states=states, weights=used)
    other_lens = "pressure" if lens == "absolute" and not weights else "absolute"
    other = scoring.rank(table, states=states, lens=other_lens)
    other_rank = {code: i + 1 for i, code in enumerate(other.dropna(subset=["score"]).index)}

    scored = ranked.dropna(subset=["score"])
    no_score = ranked[ranked["score"].isna()]
    rows = []
    for _, r in scored.head(top).iterrows():
        row = _summary(r)
        row[f"score_{other_lens}_lens"] = _n(other.at[r.name, "score"])
        row[f"rank_{other_lens}_lens"] = str(other_rank.get(r.name, "n/a"))
        rows.append(row)
    not_shown = [{"airport": c, "rank": str(i), "score": _n(r["score"]), "label": r["label"]}
                 for i, (c, r) in enumerate(scored.iloc[top:].iterrows(), start=top + 1)]
    unscored = [{"airport": c, "reason": f"{r['missing_months']:.0f} missing months; score n/a (A-19)"}
                for c, r in no_score.iterrows()]
    below = meta["below_universe"]
    below = below[below["state"].isin(states)] if states else below
    below_list = [{"airport": c, "boardings_latest_12m": _n(b)}
                  for c, b in below["boardings"].sort_values(ascending=False).items()]
    summary = (f"{len(ranked)} evaluated, {len(rows)} shown, {len(not_shown)} ranked below the top {top}, "
               f"{len(unscored)} without a score (missing months); {len(below_list)} more airports have traffic "
               f"but no more than 10,000 boardings, below the scoring universe (A-03)")
    return _result(
        {"weights_used": {k: f"{v:.2f}" for k, v in used.items()}, "lens": "custom" if weights else lens,
         "region": region or (",".join(states) if states else "national"),
         "summary": summary, "evaluated": str(len(ranked)), "shown": str(len(rows)),
         "ranking": rows, "not_shown": not_shown, "score_not_available": unscored,
         "below_universe": below_list, "normalization": NORMALIZATION},
        SCORE_FORMULA, _score_sources(), SCORE_ASSUMPTIONS,
        caveats=["No public gate counts or terminal floor area: the agent can say demand is pressing, "
                 "never that a terminal is full.",
                 "Flags marked 'low confidence' mean the score is less reliable for that airport.",
                 "'flag_checks_not_run' lists checks that had no data; 'no flags' is only true when it is empty."])


# --- 2. compare_airports ---------------------------------------------------------------------------

def compare_airports(codes: list[str]) -> dict:
    """Side by side: score, label, and the three kinds of congestion (demand, airfield, regulatory)."""
    for c in codes:
        if err := _check_code(c):
            return _error(err)
    ev = _evaluated()
    out = {}
    for c in [c.upper() for c in codes]:
        r = ev.loc[c]
        caps = [k for k in CONSTRAINTS if k["airport"] == c and k["type"] in ("cap", "curfew")]
        geometry = [k for k in CONSTRAINTS if k["airport"] == c and k["type"] == "runway"]
        out[c] = {
            **_summary(r),
            "congestion_levels": {
                "runway_atc_delay_share": f"{_pct(r['nas_share'])} of delay minutes ({_p(r['pct_nas_share'])})",
                "departures_per_effective_runway": f"{_n(r['departures_per_runway'])} a year "
                                                   f"({_p(r['pct_departures_per_runway'])})",
                "load_factor": f"{_pct(r['load_factor'])} ({_p(r['pct_load_factor'])})"},
            "demand": {"total_passengers_latest_12m_estimate": _millions(r["passengers"] * CONFIG["passengers_per_enplanement"]),
                       **_raw(r)},
            "airfield": {"effective_runways": _n(r["runways"]),
                         "runway_facts": [f"{k['statement']} [{k['id']}, {k['confidence']}]" for k in geometry]},
            "regulatory": [f"{k['statement']} [{k['id']}, {k['confidence']}]" for k in caps] or ["none on file"],
        }
    return _result(out, SCORE_FORMULA + " Three kinds of congestion are reported separately.",
                   _score_sources(), SCORE_ASSUMPTIONS + ["A-07", "A-15"],
                   caveats=["T-100 counts boardings (enplanements). Airports and legal caps usually quote total "
                            "passengers (arriving + departing), estimated here as boardings x 2 (A-07).",
                            "NAS delay share covers reporting airlines only.",
                            "A soft limit (a planning forecast) is not a legal cap and never fires the Regulatory label."])


# --- 3. route_mix ----------------------------------------------------------------------------------

def route_mix(airport: str, period: str = "latest", threshold_km: float | None = None,
              include_cargo: bool = False) -> dict:
    """Share of long-haul departures from `airport` over `period` (routing.py picks the source)."""
    airport = airport.upper()
    if airport not in ourairports.airports().index:
        return _error(f"Unknown U.S. airport code '{airport}'.")
    threshold = threshold_km or ROUTE_CFG["long_haul_km"]
    alt = ROUTE_CFG["long_haul_km_sensitivity"]
    r = routing.route(period)
    base_caveats = [f"Long-haul = great-circle distance over {threshold:,.0f} km (A-05, Eurocontrol); "
                    f"no single industry standard exists."]

    if r.source == "unsupported":
        return _result({"supported": "no", "message": r.message}, "", [], ["A-05"], "n/a", [r.message])

    if r.source == "opensky":
        flights, start, end = opensky.departures(ourairports.airports().loc[airport, "icao"])
        coords = ourairports.coordinates()
        o = ourairports.airports().loc[airport]
        dest = flights["estArrivalAirport"].fillna("")
        known = dest[dest.isin(coords.index)]
        km = pd.Series([m.great_circle_km(o["lat"], o["lon"], coords.at[d, "lat"], coords.at[d, "lon"])
                        for d in known], index=known.index, dtype=float)
        ones = pd.Series(1, index=km.index)
        return _result(
            {"window": f"{start} to {end} (UTC)", "departures": _n(len(flights)),
             "no_destination": _n(len(flights) - len(known)),
             "long_haul_share_all_flights": _pct(m.long_haul_share(km, ones, threshold)),
             f"long_haul_share_at_{alt}_km": _pct(m.long_haul_share(km, ones, alt)),
             "distance_buckets": {k: _n(v) for k, v in m.distance_buckets(km, ones).items()}},
            "departures with a known destination over the threshold / departures with a known destination",
            [f"OpenSky Network flights, {start} to {end}"], ["A-05"], "medium",
            base_caveats + ["All flights including cargo and private: OpenSky has no aircraft type, so there is "
                            "no passenger/cargo split (A-06). For a passenger-only share use a month or year.",
                            "Flights with no estimated destination are excluded from the share and counted above."])

    seg = _segments(airport, r.months)
    if seg.empty:
        return _error(f"No T-100 departures from {airport} in {r.label}.")
    passenger_kinds = ["passenger", "combi"] if ROUTE_CFG["combi_counts_as_passenger"] else ["passenger"]
    chosen = seg if include_cargo else seg[seg["aircraft"].isin(passenger_kinds)]

    def share(df, weight, thr=threshold):
        return _pct(m.long_haul_share(df["distance_km"], df[weight], thr))

    long = chosen[chosen["distance_km"] > threshold]
    top5 = (long.groupby(["DEST", "DEST_COUNTRY"]).agg(departures=("DEPARTURES_PERFORMED", "sum"),
                                                       km=("distance_km", "mean"))
            .sort_values("departures", ascending=False).head(5))
    seasons = {}
    for name, months in ROUTE_CFG["seasons"].items():           # A-27
        part = chosen[chosen["MONTH"].isin(months)]
        seasons[name] = share(part, "DEPARTURES_PERFORMED") if not part.empty else "n/a (not in window)"
    return _result(
        {"window": r.label, "counted": "all aircraft" if include_cargo else "passenger aircraft (incl. combi)",
         "unit": "departures (flights); passenger- and seat-weighted shares shown too",
         "long_haul_share": share(chosen, "DEPARTURES_PERFORMED"),
         "long_haul_share_by_passengers": share(chosen, "PASSENGERS"),
         "long_haul_share_by_seats": share(chosen, "SEATS"),
         f"long_haul_share_at_{alt}_km": share(chosen, "DEPARTURES_PERFORMED", alt),
         "long_haul_share_all_flights_incl_cargo": share(seg, "DEPARTURES_PERFORMED"),
         "departures_by_aircraft": {k: _n(v) for k, v in seg.groupby("aircraft")["DEPARTURES_PERFORMED"].sum().items()},
         "top_long_haul_destinations": [{"destination": f"{d} ({c})", "departures": _n(row["departures"]),
                                         "distance_km": _n(row["km"])} for (d, c), row in top5.iterrows()],
         "seasonal": {f"{k}_long_haul_share": v for k, v in seasons.items()},
         "distance_buckets": {k: _n(v) for k, v in m.distance_buckets(chosen["distance_km"],
                                                                      chosen["DEPARTURES_PERFORMED"]).items()}},
        "departures over the threshold / all departures in the set (great-circle distance); "
        "passenger and seat shares weight each route by passengers or seats instead",
        [f"BTS TranStats T-100 Segment (all carriers), {r.label}"], ["A-05", "A-06", "A-25", "A-26", "A-27"], "high",
        base_caveats + ["Passenger vs freighter comes from the aircraft configuration each airline files (exact).",
                        "'latest' is the same 12 months as the airport scores (A-26).",
                        "Very small operators that don't file T-100 are missing; they fly short hops, so the "
                        "long-haul share is biased slightly upward."])


def _segments(airport: str, months: list[str]) -> pd.DataFrame:
    """TranStats segments from `airport` for the given months, across calendar years if needed."""
    years = sorted({mo[:4] for mo in months})
    parts = []
    for y in years:
        one_month = [mo for mo in months if mo.startswith(y)]
        df = bts.segments(int(y), int(one_month[0][5:]) if len(months) == 1 else None)
        parts.append(df[df["ORIGIN"] == airport])
    seg = pd.concat(parts)
    ym = seg["YEAR"].astype(int).astype(str) + "-" + seg["MONTH"].astype(int).map("{:02d}".format)
    return seg[ym.isin(months)]


# --- 4. demand_signals -----------------------------------------------------------------------------

def demand_signals(airport: str) -> dict:
    """Unmet demand isn't observable, so show five traces of it, plus capacity loss per hour (A-10)."""
    if err := _check_code(airport):
        return _error(err)
    airport = airport.upper()
    ev = _evaluated()
    r = ev.loc[airport]
    level = [k for k in CONSTRAINTS if k["airport"] == airport and k["type"] == "schedule-level"]
    live = faa.status(airport)

    def trace(value: str, pct, meaning: str) -> dict:
        return {"value": value, "percentile": _p(pct), "meaning": meaning}

    traces = {
        "load_factor": trace(_pct(r["load_factor"]), r["pct_load_factor"], "how full planes are"),
        "seats_per_departure_vs_2019": trace(_signed(r["upgauging"]), r["pct_upgauging"], "bigger planes"),
        "departures_vs_2019": trace(_signed(r["departures_change"]), r["pct_departures_change"], "more or fewer flights"),
        "passengers_vs_2019": trace(_signed(r["growth_vs_2019"]), r["pct_growth_vs_2019"], "traffic recovery"),
        "runway_atc_delay_share": trace(_pct(r["nas_share"]), r["pct_nas_share"], "delays caused by runways/airspace"),
        "upgauging_signature_A09": "yes" if r["upgauging_signature"] else "no (display-only)",
        "schedule_level": [f"{k['statement']} [{k['id']}, {k['confidence']}]" for k in level] or ["none on file"],
        "live_delay_programs": _live_text(live),
    }
    values = {"airport": airport, "label": r["label"], "label_evidence": r["label_evidence"],
              "near_misses": r["near_misses"], "traces": traces}

    # How much (A-24): passengers missing vs the peer group's recovery since 2019, in boardings and flights.
    peers = ev[ev["hub_class"] == r["hub_class"]]
    median = peers["growth_vs_2019"].median()
    gap = m.recovery_gap(r["growth_vs_2019"], median, r["passengers_2019"])
    per_flight = r["seats_per_departure"] * r["load_factor"]
    values["recovery_gap_estimate"] = {
        "airport_recovery_vs_2019": _signed(r["growth_vs_2019"]),
        "peer_median_recovery_vs_2019": _signed(median),
        "boardings": _millions(gap), "departures_equivalent": _n(gap / per_flight),
        "label": "estimate (A-24): peer recovery minus this airport's, times its 2019 boardings"}

    caveats = ["Unmet demand is not directly observable; these are indirect traces and two estimates.",
               "Up-gauging also reflects fleet strategy and pilot shortages (A-09).",
               "The recovery gap assumes the airport would have recovered like its peers; other causes "
               "(e.g. weaker routes) would also widen it (A-24)."]
    rates = [k for k in CONSTRAINTS if k["airport"] == airport and "reference_arrival_rate" in k["value"]]
    if rates:
        v, hours = rates[0]["value"], CONFIG["capacity"]["operating_hours_per_day"]
        lost, share = m.capacity_loss_per_hour(v["reference_arrival_rate"], v["current_arrival_rate"])
        flights, pax = m.capacity_upper_bound(lost, hours, r["seats_per_departure"], r["load_factor"])
        values["capacity_loss_per_hour"] = (f"{v['reference_arrival_rate']} -> {v['current_arrival_rate']} arrivals "
                                            f"per hour = {lost} fewer ({_pct(share)}) [{rates[0]['id']}]")
        values["capacity_loss_upper_bound"] = {
            "hours": f"{hours} hours a day (A-10)", "arrivals_per_day": _n(flights),
            "passengers_per_day": _n(pax), "passengers_per_year": _millions(pax * 365),
            "label": "upper bound: every lost clear-weather slot filled all day, at today's "
                     f"{_n(r['seats_per_departure'])} seats per flight and {_pct(r['load_factor'])} load factor"}
        values["live_arrival_rate"] = _n(live["arrival_rate"]) if live["arrival_rate"] else "not reported now"
        caveats.append("The capacity-loss figure is an upper bound (A-10): low visibility and off-peak hours "
                       "make the real loss smaller.")

    values["timing"] = _timing(airport)
    return _result(values, "traces from T-100 metrics, the KB and FAA live status; recovery gap = (peer median "
                           "recovery - airport recovery) x 2019 boardings; capacity upper bound = lost arrivals per "
                           "hour x hours x seats per flight x load factor",
                   [_table()[1]["score_window"], "kb/constraints.yaml", "FAA NAS Status (live)"],
                   ["A-04", "A-09", "A-10", "A-16", "A-24"], "medium", caveats)


def _timing(airport: str) -> dict:
    """Data window end vs each dated constraint: how much of the window reflects it."""
    end = _table()[1]["score_period"][1]
    out = []
    for k in CONSTRAINTS:
        date = k["airport"] == airport and k["value"].get("effective_date")
        if not date:
            continue
        months = (pd.Period(end, "M") - pd.Period(date[:7], "M")).n
        if months < 0:
            note = f"takes effect after the data window ends ({end}): not reflected in the traffic data"
        elif months < 12:
            note = f"only about {months} month(s) of the 12-month data window (to {end}) reflect it"
        else:
            note = ""
        out.append({"id": k["id"], "effective": str(date), "note": note})
    return {"data_window_end": end, "constraints": out}


def _live_text(s: dict) -> str:
    if not s["listed"]:
        return "no active FAA event right now"
    parts = []
    if s["ground_delay"]:
        g = s["ground_delay"]
        parts.append(f"ground delay program (avg {g['avg_minutes']} min, {g['reason']})")
    if s["ground_stop"]:
        parts.append("ground stop")
    if s["arrival_rate"]:
        parts.append(f"arrival rate {s['arrival_rate']}/hour")
    return "; ".join(parts) or "listed by FAA (closure or notice), no delay program"


# --- 5-7. Facts, live status, assumptions ----------------------------------------------------------

def get_constraints(airport: str) -> dict:
    airport = airport.upper()
    facts = [{"id": k["id"], "type": k["type"], "statement": k["statement"], "confidence": k["confidence"],
              "source": k["source_url"] or "none yet", "verified_on": str(k["verified_on"] or "not verified")}
             for k in CONSTRAINTS if k["airport"] == airport]
    return _result({"airport": airport, "facts": facts or "no constraints on file"}, "lookup",
                   ["kb/constraints.yaml"], [], "high" if facts else "n/a",
                   [] if facts else [f"No curated constraints for {airport}; absence of a fact is not proof of no constraint."])


def live_status(airport: str) -> dict:
    s = faa.status(airport.upper())
    return _result({"airport": airport.upper(), "status": _live_text(s), "as_of": s.get("as_of") or "now"},
                   "FAA NAS Status airport events", ["FAA NAS Status (live)"], [], "high",
                   ["FAA lists only airports with an active event; not listed = no active event."])


def get_assumption(assumption_id: str) -> dict:
    a = ASSUMPTIONS.get(assumption_id.upper())
    if not a:
        return _error(f"Unknown assumption '{assumption_id}'. Known: {', '.join(ASSUMPTIONS)}.")
    return _result({k: a[k] for k in ("id", "statement", "value", "why", "alternatives_considered", "sensitivity")},
                   "lookup", ["kb/assumptions.yaml"], [a["id"]])
