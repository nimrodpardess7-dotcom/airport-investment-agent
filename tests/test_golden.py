"""Golden tests: the four assignment questions, answered by calling tools directly (no LLM).

These hit the live APIs (through the cache), so they assert structure and sanity ranges, not exact values.
Run: python -m pytest tests/test_golden.py
"""

import os
import re

import pytest
from dotenv import load_dotenv

import tools
from config import ROOT

load_dotenv(ROOT / ".env")

SHAPE = {"values", "formula", "sources", "assumptions", "confidence", "caveats"}


def pct(s: str) -> float:
    return float(re.match(r"[+-]?[\d.]+", s.lstrip("p")).group()) if s not in ("n/a",) else float("nan")


# --- Q1: New England terminal candidates -----------------------------------------------------------

def test_q1_new_england_both_lenses():
    absolute = tools.rank_airports(region="new_england", lens="absolute")
    pressure = tools.rank_airports(region="new_england", lens="pressure")
    for res in (absolute, pressure):
        assert set(res) == SHAPE
        assert all(r["state"] in {"CT", "ME", "MA", "NH", "RI", "VT"} for r in res["values"]["ranking"])
        assert all(r["label"] in {"Regulatory", "Airfield", "Terminal", "None evident"} for r in res["values"]["ranking"])
    bos = next(r for r in absolute["values"]["ranking"] if r["airport"] == "BOS")
    assert pct(bos["scale"]) >= 90                       # BOS wins on scale
    assert pressure["values"]["weights_used"]["scale"] == "0.00"
    assert any("gate" in c for c in absolute["caveats"])   # no gate data, said out loud


def test_q1_what_if_weights_are_validated():
    res = tools.rank_airports(region="new_england", weights={"growth": 2, "pressure": 1, "scale": 1})
    assert res["values"]["weights_used"] == {"growth": "0.50", "pressure": "0.25", "scale": "0.25"}
    assert "error" in tools.rank_airports(region="new_england", weights={"growth": -1, "pressure": 1, "scale": 1})["values"]


# --- Q2: LAX vs SNA --------------------------------------------------------------------------------

def test_q2_lax_vs_sna():
    res = tools.compare_airports(["LAX", "SNA"])
    v = res["values"]
    assert v["SNA"]["label"] == "Regulatory"            # capped by law
    assert any("SNA-01" in s for s in v["SNA"]["regulatory"])
    assert v["LAX"]["label"] != "Regulatory"            # soft limit never fires Regulatory
    assert any("LAX-01" in s for s in v["LAX"]["regulatory"])
    for code in ("LAX", "SNA"):
        assert {"demand", "airfield", "regulatory"} <= set(v[code])


# --- Q3: % long-haul out of ANC --------------------------------------------------------------------

def test_q3_anc_latest_year():
    res = tools.route_mix("ANC", "latest")
    v = res["values"]
    assert v["counted"] == "passenger aircraft only"
    assert 0 < pct(v["long_haul_share"]) < pct(v["long_haul_share_all_aircraft"])   # freighters fly longer
    assert pct(v["long_haul_share"]) <= pct(v["long_haul_share_at_3500_km"])         # lower threshold, higher share
    assert "freighter" in v["departures_by_aircraft"]
    assert any("A-05" in c for c in res["caveats"])


def test_q3_unsupported_day_offers_nearest():
    v = tools.route_mix("ANC", "2024-03-03")["values"]
    assert v["supported"] == "no" and "2024-03" in v["message"]


@pytest.mark.skipif(not os.getenv("OPENSKY_CLIENT_ID"), reason="OpenSky keys not set (optional)")
def test_q3_last_7_days_has_no_cargo_split():
    res = tools.route_mix("ANC", "last_7_days")
    assert "long_haul_share_all_flights" in res["values"]
    assert any("no passenger/cargo split" in c for c in res["caveats"])


# --- Q4: SFO unmet demand --------------------------------------------------------------------------

def test_q4_sfo_demand_signals():
    res = tools.demand_signals("SFO")
    v = res["values"]
    assert v["label"] == "Airfield"
    assert len(v["traces"]) == 5
    assert "54 -> 40" in v["capacity_loss_per_hour"] and "14 fewer" in v["capacity_loss_per_hour"]
    assert any("not directly observable" in c for c in res["caveats"])


# --- Edge cases from the eval set ------------------------------------------------------------------

def test_unknown_airport_code():
    assert "error" in tools.compare_airports(["XYZ"])["values"]


def test_assumption_lookup():
    v = tools.get_assumption("A-05")["values"]
    assert v["id"] == "A-05" and "4,000" in v["statement"]


@pytest.mark.parametrize("period, source", [("last_7_days", "opensky"), ("2025", "transtats"),
                                            ("2025-Q3", "transtats"), ("2025-07", "transtats"),
                                            ("2024-03-03", "unsupported"), ("2099", "unsupported")])
def test_routing(period, source):
    import routing
    assert routing.route(period).source == source
