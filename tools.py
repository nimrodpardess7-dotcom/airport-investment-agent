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


def _summary(row: pd.Series) -> dict:
    return {
        "airport": row.name, "name": row["name"], "state": row["state"], "peer_group": row["hub_class"],
        "score": _n(row["score"]), "growth": _p(row["growth"]), "pressure": _p(row["pressure"]),
        "scale": _p(row["scale"]), "label": row["label"], "label_reasons": row["label_reasons"],
        "flags": row["flags"],
    }


SCORE_FORMULA = ("score = w_growth x Growth + w_pressure x Pressure + w_scale x Scale (0-100). "
                 "Growth = mean percentile of (latest 12 months vs 2019) and (CAGR since 2022); "
                 "Pressure = mean percentile of load factor and up-gauging (seats per departure vs 2019); "
                 "Scale = percentile of passengers vs all airports. Growth/Pressure percentiles are within the "
                 "FAA hub-class peer group. Label: first match of Regulatory, Airfield, Terminal, None evident.")
SCORE_ASSUMPTIONS = ["A-01", "A-02", "A-03", "A-04", "A-12", "A-13", "A-14", "A-16", "A-18", "A-19", "A-20"]


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
    ranked = scoring.rank(_table()[0], states=states, weights=used)
    rows = [_summary(r) for _, r in ranked.head(top).iterrows()]
    return _result(
        {"weights_used": {k: f"{v:.2f}" for k, v in used.items()}, "lens": "custom" if weights else lens,
         "region": region or (",".join(states) if states else "national"),
         "airports_ranked": str(len(ranked)), "ranking": rows},
        SCORE_FORMULA, _score_sources(), SCORE_ASSUMPTIONS,
        caveats=["No public gate counts or terminal floor area: the agent can say demand is pressing, "
                 "never that a terminal is full.",
                 "Flags marked 'low confidence' mean the score is less reliable for that airport."])


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
            "demand": {"passengers_latest_12m": _millions(r["passengers"]),
                       "growth_vs_2019": _signed(r["growth_vs_2019"]), "load_factor": _pct(r["load_factor"]),
                       "upgauging_vs_2019": _signed(r["upgauging"]),
                       "departures_change_vs_2019": _signed(r["departures_change"])},
            "airfield": {"nas_delay_share": _pct(r["nas_share"]), "nas_delay_share_percentile": _p(r["pct_nas_share"]),
                         "effective_runways": _n(r["runways"]),
                         "departures_per_runway_percentile_display_only": _p(r["pct_departures_per_runway"]),
                         "runway_facts": [f"{k['statement']} [{k['id']}, {k['confidence']}]" for k in geometry]},
            "regulatory": [f"{k['statement']} [{k['id']}, {k['confidence']}]" for k in caps] or ["none on file"],
        }
    return _result(out, SCORE_FORMULA + " Three kinds of congestion are reported separately.",
                   _score_sources(), SCORE_ASSUMPTIONS + ["A-07", "A-15"],
                   caveats=["NAS delay share covers reporting airlines only.",
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

    seg = bts.segments(r.year, r.months[0] if r.months and len(r.months) == 1 else None)
    seg = seg[seg["ORIGIN"] == airport]
    if r.months:
        seg = seg[seg["MONTH"].isin(r.months)]
    if seg.empty:
        return _error(f"No T-100 departures from {airport} in {r.label}.")
    dep_by_type = seg.groupby("aircraft")["DEPARTURES_PERFORMED"].sum()
    passenger = seg[seg["aircraft"] == "passenger"]
    chosen = seg if include_cargo else passenger
    km, dep = chosen["distance_km"], chosen["DEPARTURES_PERFORMED"]
    return _result(
        {"window": r.label, "counted": "all aircraft" if include_cargo else "passenger aircraft only",
         "long_haul_share": _pct(m.long_haul_share(km, dep, threshold)),
         f"long_haul_share_at_{alt}_km": _pct(m.long_haul_share(km, dep, alt)),
         "long_haul_share_all_aircraft": _pct(m.long_haul_share(seg["distance_km"], seg["DEPARTURES_PERFORMED"], threshold)),
         "departures_by_aircraft": {k: _n(v) for k, v in dep_by_type.items()},
         "distance_buckets": {k: _n(v) for k, v in m.distance_buckets(km, dep).items()}},
        "departures over the threshold / all departures in the set (departure-weighted, great-circle distance)",
        [f"BTS TranStats T-100 Segment (all carriers), {r.label}"], ["A-05", "A-06"], "high",
        base_caveats + ["Passenger vs freighter comes from the aircraft configuration each airline files (exact).",
                        "Very small operators that don't file T-100 are missing; they fly short hops, so the "
                        "long-haul share is biased slightly upward."])


# --- 4. demand_signals -----------------------------------------------------------------------------

def demand_signals(airport: str) -> dict:
    """Unmet demand isn't observable, so show five traces of it, plus capacity loss per hour (A-10)."""
    if err := _check_code(airport):
        return _error(err)
    airport = airport.upper()
    r = _evaluated().loc[airport]
    level = [k for k in CONSTRAINTS if k["airport"] == airport and k["type"] == "schedule-level"]
    live = faa.status(airport)
    traces = {
        "1_load_factor": f"{_pct(r['load_factor'])} ({_p(r['pct_load_factor'])} of peers)",
        "2_upgauging_vs_departures": (f"seats per departure {_signed(r['upgauging'])} vs 2019 while departures "
                                      f"{_signed(r['departures_change'])}; A-09 signature: "
                                      f"{'yes' if r['upgauging_signature'] else 'no'} (display-only)"),
        "3_passengers_vs_flights_since_2019": (f"passengers {_signed(r['growth_vs_2019'])}, "
                                               f"departures {_signed(r['departures_change'])}"),
        "4_schedule_level": [f"{k['statement']} [{k['id']}, {k['confidence']}]" for k in level] or ["none on file"],
        "5_live_delay_programs": _live_text(live),
    }
    values = {"airport": airport, "label": r["label"], "label_reasons": r["label_reasons"], "traces": traces}
    caveats = ["Unmet demand is not directly observable; these are indirect traces.",
               "Up-gauging also reflects fleet strategy and pilot shortages (A-09)."]
    rates = [k for k in CONSTRAINTS if k["airport"] == airport and "reference_arrival_rate" in k["value"]]
    if rates:
        v = rates[0]["value"]
        lost, share = m.capacity_loss_per_hour(v["reference_arrival_rate"], v["current_arrival_rate"])
        values["capacity_loss_per_hour"] = (f"{v['reference_arrival_rate']} -> {v['current_arrival_rate']} arrivals "
                                            f"per hour = {lost} fewer ({_pct(share)}) [{rates[0]['id']}]")
        values["live_arrival_rate"] = _n(live["arrival_rate"]) if live["arrival_rate"] else "not reported now"
        caveats.append("Capacity loss is per hour in clear weather from documented rates; no daily extrapolation (A-10).")
    return _result(values, "five traces from T-100 metrics, the KB and FAA live status; capacity loss = "
                           "reference rate - current rate",
                   [_table()[1]["score_window"], "kb/constraints.yaml", "FAA NAS Status (live)"],
                   ["A-04", "A-09", "A-10", "A-16"], "medium", caveats)


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
