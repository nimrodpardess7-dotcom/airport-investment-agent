"""Golden tests for the answer-quality review (P0/P1). Each one reproduced an issue before it was fixed.

These call the tools directly on live (cached) data; no LLM.
"""

import re

import pytest

import tools
from config import ASSUMPTIONS, CONFIG, CONSTRAINTS, ROOT

NE = CONFIG["regions"]["new_england"]


def ranking(**kw):
    return tools.rank_airports(region="new_england", **kw)["values"]


# --- P0.1 Silent exclusions ------------------------------------------------------------------------

def test_ranking_accounts_for_every_airport():
    v = ranking(top=10)
    shown = {r["airport"] for r in v["ranking"]}
    below_top = {r["airport"] for r in v["not_shown"]}
    assert int(v["evaluated"]) == len(shown) + len(below_top) + len(v["score_not_available"])
    assert {"ACK", "MHT"} <= below_top                       # were silently cut by top=10
    assert any(x["airport"] == "BHB" for x in v["below_universe"])   # A-03 exclusion, stated
    assert v["summary"].startswith(f"{v['evaluated']} evaluated, {v['shown']} shown")


# --- P0.2 Magnitudes next to percentiles -----------------------------------------------------------

RAW = ["boardings_latest_12m", "growth_vs_2019", "cagr_since_2022", "load_factor",
       "seats_per_departure_change_vs_2019", "departures_change_vs_2019"]


def test_ranking_rows_carry_raw_values():
    row = ranking(top=3)["ranking"][0]
    for key in RAW:
        assert key in row["raw"] and row["raw"][key] != ""


def test_demand_signals_have_a_percentile_per_trace():
    traces = tools.demand_signals("SFO")["values"]["traces"]
    numeric = {k: t for k, t in traces.items() if isinstance(t, dict)}
    assert len(numeric) >= 4
    assert all(re.fullmatch(r"p\d+", t["percentile"]) for t in numeric.values())


# --- P0.3 Labels show what triggered them ----------------------------------------------------------

def test_label_evidence_is_structured():
    row = next(r for r in ranking(top=10)["ranking"] if r["airport"] == "PWM")   # None evident
    ev = row["label_evidence"]
    assert {"rule", "metric", "value", "percentile", "threshold", "passed"} <= set(ev[0])
    assert any(not c["passed"] for c in ev)               # says which condition failed
    assert "near_misses" in row


# --- P0.4 Flags the Q1 answer missed ---------------------------------------------------------------

def test_hvn_flags_carrier_ulcc_low_base_and_project():
    hvn = next(r for r in ranking(top=10)["ranking"] if r["airport"] == "HVN")
    text = " ".join(hvn["flags"])
    assert "carrier" in text and "ultra-low-cost" in text and "low base" in text
    assert hvn["flag_checks_not_run"] == []               # all checks ran, so "no flags" would be legitimate
    assert any(k["type"] == "project" for k in CONSTRAINTS if k["airport"] == "HVN")


# --- P0.5 SFO: how much -----------------------------------------------------------------------------

def test_sfo_how_much_and_timing():
    v = tools.demand_signals("SFO")["values"]
    assert "recovery_gap_estimate" in v and "M" in v["recovery_gap_estimate"]["boardings"]
    ub = v["capacity_loss_upper_bound"]
    assert {"arrivals_per_day", "passengers_per_day", "hours"} <= set(ub)
    timing = v["timing"]
    assert timing["data_window_end"] == tools._table()[1]["score_period"][1]
    assert any("SFO-02" in c["id"] and c["note"] for c in timing["constraints"])


# --- P1.6 Route mix ---------------------------------------------------------------------------------

def test_route_mix_weights_destinations_and_seasons():
    v = tools.route_mix("ANC", "latest")["values"]
    for key in ("long_haul_share_by_passengers", "long_haul_share_by_seats", "top_long_haul_destinations",
                "seasonal"):
        assert key in v
    assert 1 <= len(v["top_long_haul_destinations"]) <= 5


# --- P1.7 One time-window rule ---------------------------------------------------------------------

def test_route_mix_latest_uses_the_score_window():
    s, e = tools._table()[1]["score_period"]
    assert tools.route_mix("ANC", "latest")["values"]["window"] == f"{s} to {e}"


# --- P1.8 Register alignment -----------------------------------------------------------------------

def test_every_cited_id_exists():
    kb_ids = {k["id"] for k in CONSTRAINTS}
    files = [*ROOT.glob("*.py"), ROOT / "prompts" / "system.md", ROOT / "config.yaml"]
    cited_a = set()
    for f in files:
        cited_a |= set(re.findall(r"\bA-\d{2}[a-z]?\b", f.read_text(encoding="utf-8")))
    assert cited_a - set(ASSUMPTIONS) == set(), f"unknown assumption ids: {cited_a - set(ASSUMPTIONS)}"
    cited_kb = set()
    for f in files:
        cited_kb |= set(re.findall(r"\b(?:SNA|LAX|SFO|HVN)-\d{2}\b", f.read_text(encoding="utf-8")))
    assert cited_kb - kb_ids == set(), f"unknown KB ids: {cited_kb - kb_ids}"


# --- P1.9 Both lenses ------------------------------------------------------------------------------

def test_ranking_shows_both_lenses():
    row = ranking(top=3)["ranking"][0]
    assert "score_pressure_lens" in row and "rank_pressure_lens" in row
