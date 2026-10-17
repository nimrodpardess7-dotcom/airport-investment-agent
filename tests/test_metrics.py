"""Unit tests for metrics.py. Every expected value is computed by hand and written out as arithmetic."""

import math

import pandas as pd
import pytest

import metrics as m

CUTOFFS = {"large": 0.01, "medium": 0.0025, "small": 0.0005}


def monthly_fixture() -> pd.DataFrame:
    """Two airports. AAA flies all 3 months; BBB misses February."""
    return pd.DataFrame([
        ("AAA", "2026-01", 10, 1000, 1200),
        ("AAA", "2026-02", 10, 500, 1200),
        ("AAA", "2026-03", 20, 1500, 2400),
        ("BBB", "2026-01", 5, 300, 400),
        ("BBB", "2026-03", 5, 100, 400),
    ], columns=["airport", "month", "departures", "passengers", "seats"])


# --- windows ---

def test_latest_12_window():
    assert m.latest_12_window("2026-04") == ("2025-05", "2026-04")
    assert m.latest_12_window("2026-12") == ("2026-01", "2026-12")


def test_years_between():
    assert m.years_between("2022-12", "2026-04") == pytest.approx(40 / 12)


# --- totals ---

def test_totals_sums_and_counts_months():
    t = m.totals(monthly_fixture(), "2026-01", "2026-03")
    assert t.loc["AAA"].tolist() == [40, 3000, 4800, 3]
    assert t.loc["BBB"].tolist() == [10, 400, 800, 2]  # February missing -> 2 months (A-19)


def test_totals_respects_window():
    t = m.totals(monthly_fixture(), "2026-02", "2026-03")
    assert t.loc["AAA", "passengers"] == 500 + 1500


# --- ratios ---

def test_load_factor():
    assert m.load_factor(3000, 4800) == pytest.approx(0.625)


def test_ratio_zero_denominator_is_nan():
    assert math.isnan(m.ratio(5, 0))
    s = m.ratio(pd.Series([1, 2]), pd.Series([0, 4]))
    assert math.isnan(s[0]) and s[1] == 0.5


def test_growth():
    assert m.growth(110, 100) == pytest.approx(0.10)
    assert m.growth(80, 100) == pytest.approx(-0.20)


def test_cagr():
    # 100 -> 121 over 2 years = 10% a year (1.1 * 1.1 = 1.21)
    assert m.cagr(121, 100, 2) == pytest.approx(0.10)


def test_upgauging():
    # base: 1000 seats / 10 dep = 100 per flight; now: 1100 / 10 = 110 per flight -> +10%
    assert m.upgauging(1100, 10, 1000, 10) == pytest.approx(0.10)
    # fewer, bigger flights: now 1000 / 8 = 125 per flight vs 100 -> +25%
    assert m.upgauging(1000, 8, 1000, 10) == pytest.approx(0.25)


def test_departures_per_runway():
    assert m.departures_per_runway(50000, 2) == 25000
    assert math.isnan(m.departures_per_runway(50000, 0))


def test_seasonality_ratio():
    s = m.seasonality_ratio(monthly_fixture(), "2026-01", "2026-03")
    assert s["AAA"] == pytest.approx(1500 / 500)   # 3.0 -> highly seasonal at A-18's 2.0
    assert s["BBB"] == pytest.approx(300 / 100)


def test_nas_share():
    delays = pd.DataFrame({"airport": ["SFO", "SFO", "PVD"],
                           "nas_delay": [40, 10, 5], "arr_delay": [60, 40, 50]})
    s = m.nas_share(delays)
    assert s["SFO"] == pytest.approx(50 / 100)
    assert s["PVD"] == pytest.approx(5 / 50)


def test_freighter_share():
    seg = pd.DataFrame({"ORIGIN": ["ANC", "ANC", "ANC", "BOS"],
                        "aircraft": ["passenger", "freighter", "combi", "passenger"],
                        "DEPARTURES_PERFORMED": [40, 55, 5, 100]})
    s = m.freighter_share(seg)
    assert s["ANC"] == pytest.approx(55 / 100)
    assert s["BOS"] == 0


# --- peer group ---

@pytest.mark.parametrize("share, expected", [
    (0.02, "large"), (0.01, "large"), (0.005, "medium"), (0.0025, "medium"),
    (0.001, "small"), (0.0005, "small"), (0.0001, "non-hub"),
])
def test_hub_class(share, expected):
    assert m.hub_class(share, CUTOFFS) == expected


def test_is_borderline():
    assert m.is_borderline(0.0095, CUTOFFS, 0.10)      # 5% below the 1% cutoff
    assert not m.is_borderline(0.005, CUTOFFS, 0.10)   # mid-way between cutoffs


# --- route mix ---

def test_great_circle_km_one_degree_of_latitude():
    # 1 degree of latitude = 2 * pi * 6371 / 360 = 111.19 km
    assert m.great_circle_km(0, 0, 1, 0) == pytest.approx(2 * math.pi * 6371 / 360)


def test_long_haul_share_is_departure_weighted():
    km = pd.Series([1000, 5000, 9000])
    dep = pd.Series([6, 3, 1])
    assert m.long_haul_share(km, dep, 4000) == pytest.approx((3 + 1) / 10)
    assert m.long_haul_share(km, dep, 3500) == pytest.approx((3 + 1) / 10)
    assert m.long_haul_share(km, dep, 6000) == pytest.approx(1 / 10)


def test_distance_buckets():
    km = pd.Series([1000, 1500, 5000, 9000])
    dep = pd.Series([1, 2, 3, 4])
    assert m.distance_buckets(km, dep) == {"< 1,500 km": 1, "1,500-4,000 km": 2,
                                           "4,000-8,000 km": 3, "> 8,000 km": 4}


# --- carriers and estimates ---

def test_carrier_shares():
    seg = pd.DataFrame({"ORIGIN": ["AAA"] * 3, "UNIQUE_CARRIER": ["XP", "XP", "DL"],
                        "aircraft": ["passenger", "combi", "passenger"], "SEATS": [60, 20, 20]})
    s = m.carrier_shares(seg, ["XP"]).loc["AAA"]
    assert s["top_carrier"] == "XP" and s["top_carrier_share"] == pytest.approx(80 / 100)
    assert s["ulcc_share"] == pytest.approx(80 / 100)
    assert m.carrier_shares(seg, ["XP"], include_combi=False).loc["AAA", "top_carrier_share"] == pytest.approx(60 / 80)


def test_recovery_gap():
    # Peers recovered +2%, airport -4%: gap 6 points of a 1,000,000 base = 60,000.
    assert m.recovery_gap(-0.04, 0.02, 1_000_000) == pytest.approx(60_000)
    assert m.recovery_gap(0.05, 0.02, 1_000_000) == 0


def test_capacity_upper_bound():
    flights, pax = m.capacity_upper_bound(14, 17, 170, 0.8)
    assert flights == 14 * 17 and pax == pytest.approx(14 * 17 * 170 * 0.8)


# --- airfield capacity ---

def test_capacity_loss_per_hour():
    lost, share = m.capacity_loss_per_hour(54, 40)
    assert lost == 14
    assert share == pytest.approx(14 / 54)
