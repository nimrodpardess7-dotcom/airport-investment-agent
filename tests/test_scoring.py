"""Unit tests for scoring.py on a hand-made table: percentiles, weights, score, label order, flags."""

import math

import pandas as pd
import pytest

import scoring as s

# Fake KB: CAP has a hard 10M passenger cap; GEO has a close-parallel runway entry; SOFT a soft cap.
FAKE_KB = [
    {"id": "CAP-01", "airport": "CAP", "type": "cap", "value": {"annual_passengers": 10_000_000, "hard": True}},
    {"id": "GEO-01", "airport": "GEO", "type": "runway", "value": {"geometry": "close_parallel"}},
    {"id": "SOFT-01", "airport": "SOFT", "type": "cap", "value": {"annual_passengers": 1_000_000, "hard": False}},
]


@pytest.fixture(autouse=True)
def fake_kb(monkeypatch):
    monkeypatch.setattr(s, "CONSTRAINTS", FAKE_KB)


def table() -> pd.DataFrame:
    """Four airports in one peer group. Values chosen so each rank is obvious (1 = lowest)."""
    rows = {
        #          pax        growth19 cagr  LF    upg   depchg dep/rwy nas   season frt  missing
        "CAP":  [4_500_000, 0.10, 0.05, 0.85, 0.05, 0.00, 50000, 0.10, 1.2, 0.00, 0],
        "GEO":  [3_000_000, -0.05, 0.01, 0.80, 0.02, -0.10, 20000, 0.20, 1.3, 0.01, 0],
        "HOT":  [2_000_000, 0.30, 0.10, 0.90, 0.20, -0.05, 10000, 0.05, 1.1, 0.02, 0],
        "SOFT": [1_000_000, 0.00, 0.00, 0.70, 0.00, 0.10, 5000, 0.08, 2.5, 0.40, 1],
    }
    cols = ["passengers", "growth_vs_2019", "cagr_since_2022", "load_factor", "upgauging", "departures_change",
            "departures_per_runway", "nas_share", "seasonality", "freighter_share", "missing_months"]
    t = pd.DataFrame.from_dict(rows, orient="index", columns=cols)
    t["hub_class"], t["borderline_class"], t["state"] = "medium", False, ["CA", "CA", "MA", "MA"]
    return t


# --- percentiles ---

def test_percentile_is_rank_within_group():
    v = pd.Series([10, 20, 30, 40, 5], index=list("abcde"))
    g = pd.Series(["x", "x", "x", "x", "y"], index=list("abcde"))
    p = s.percentile(v, g)
    assert p.tolist() == [25, 50, 75, 100, 100]   # e is alone in group y -> 100


def test_percentile_keeps_missing():
    p = s.percentile(pd.Series([1, None, 3]), pd.Series(["x", "x", "x"]))
    assert math.isnan(p[1])


# --- weights ---

def test_validate_weights_normalizes():
    assert s.validate_weights({"growth": 2, "pressure": 1, "scale": 1}) == {"growth": 0.5, "pressure": 0.25, "scale": 0.25}


@pytest.mark.parametrize("bad", [
    {"growth": 1, "pressure": 1},                        # missing component
    {"growth": -1, "pressure": 1, "scale": 1},           # negative
    {"growth": 0, "pressure": 0, "scale": 0},            # all zero
])
def test_validate_weights_rejects(bad):
    with pytest.raises(ValueError):
        s.validate_weights(bad)


# --- score ---

def test_score_components_and_weighting():
    out = s.score(table(), {"growth": 0.35, "pressure": 0.35, "scale": 0.30})
    hot = out.loc["HOT"]
    # HOT ranks 4th of 4 on growth_vs_2019, cagr, load factor and upgauging -> 100 on each.
    assert hot["growth"] == 100 and hot["pressure"] == 100
    # HOT is 2nd smallest by passengers -> p50.
    assert hot["scale"] == 50
    assert hot["score"] == pytest.approx(0.35 * 100 + 0.35 * 100 + 0.30 * 50)


def test_pressure_lens_ignores_scale():
    out = s.score(table(), s.lens_weights("pressure"))
    hot = out.loc["HOT"]
    assert hot["score"] == pytest.approx(0.5 * 100 + 0.5 * 100)


def test_missing_months_blanks_the_score():
    t = table()
    t.loc["HOT", "missing_months"] = 4   # A-19: more than 3 missing -> n/a
    out = s.score(t, s.lens_weights("absolute"))
    assert math.isnan(out.loc["HOT", "score"])


# --- label (first match wins) ---

def labelled():
    return s.evaluate(table(), lens="absolute")


def test_regulatory_beats_everything():
    # CAP: 4.5M boardings x 2 = 9M passengers = 90% of its 10M hard cap (>= 85%).
    out = labelled()
    assert out.loc["CAP", "label"] == "Regulatory"
    assert "90%" in out.loc["CAP", "label_reasons"][0]


def test_soft_cap_never_fires_regulatory():
    # SOFT: 1M x 2 = 2M passengers = 200% of a 1M cap, but the cap is soft.
    assert labelled().loc["SOFT", "label"] != "Regulatory"


def test_airfield_from_runway_geometry():
    out = labelled()
    assert out.loc["GEO", "label"] == "Airfield"
    assert any("GEO-01" in r for r in out.loc["GEO", "label_reasons"])


def test_terminal_when_growth_and_pressure_high():
    # HOT: growth and pressure p100, departures per runway and NAS share low.
    assert labelled().loc["HOT", "label"] == "Terminal"


def test_none_evident():
    assert labelled().loc["SOFT", "label"] == "None evident"


# --- flags and display ---

def test_flags():
    f = labelled().loc["SOFT", "flags"]
    assert any("seasonal" in x for x in f)       # 2.5 >= 2.0 (A-18)
    assert any("missing" in x for x in f)        # 1 missing month (A-19)
    assert any("cargo-heavy" in x for x in f)    # 40% >= 25% (A-20)
    assert labelled().loc["HOT", "flags"] == []


def test_scale_is_ranked_nationally_growth_within_group():
    t = table()
    t.loc[["CAP", "GEO"], "hub_class"] = "large"     # two groups of two
    out = s.score(t, s.lens_weights("absolute"))
    # Scale: CAP is biggest of all four -> p100; HOT is 2nd smallest of four -> p50.
    assert out.loc["CAP", "scale"] == 100 and out.loc["HOT", "scale"] == 50
    # Growth: HOT is top of its own group (HOT, SOFT) -> p100; GEO is bottom of (CAP, GEO) -> p50.
    assert out.loc["HOT", "growth"] == 100 and out.loc["GEO", "growth"] == 50


def test_busy_runways_alone_do_not_fire_airfield():
    # CAP has the most departures per runway (p100) but low NAS share; without its cap it is not Airfield.
    t = table()
    t.index = ["NOCAP" if i == "CAP" else i for i in t.index]
    t.loc["NOCAP", "nas_share"] = 0.01   # lowest of four -> p25
    assert s.evaluate(t, lens="absolute").loc["NOCAP", "label"] != "Airfield"


def test_rank_filters_after_national_percentiles():
    ma = s.rank(table(), states=["MA"], lens="absolute")
    assert set(ma.index) == {"HOT", "SOFT"}
    # HOT's percentiles still come from all four airports.
    assert ma.loc["HOT", "scale"] == 50
