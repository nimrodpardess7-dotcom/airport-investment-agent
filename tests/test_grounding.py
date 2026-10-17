"""Unit tests for grounding.py: which numbers pass, which are flagged, and why."""

import json

import grounding as g

TOOL = json.dumps({"values": {"utilization": "92%", "passengers": "36.59M", "scale": "p96",
                              "departures": "48,963", "share": "11.4%", "change": "-15.7%",
                              "loss": "54 -> 40 arrivals per hour = 14 fewer (25.9%)"},
                   "sources": ["T-100 summary, 2025-05 to 2026-04"]})


def test_quoted_numbers_pass():
    answer = ("SNA is at 92% of its cap; LAX carried 36.59M passengers (-15.7% vs 2019), scale p96. "
              "ANC: 48,963 freighter departures; 11.4% long-haul. SFO lost 14 arrivals per hour (54 to 40, 25.9%).")
    assert g.check(answer, [TOOL]) == []


def test_invented_number_is_flagged():
    assert g.check("LAX is at 37% of capacity.", [TOOL]) == ["37"]


def test_rounded_number_is_flagged():
    # The tool said 36.59M; rounding to 36.6M is a different number the reader can't trace.
    assert g.check("LAX carried 36.6M passengers.", [TOOL]) == ["36.6"]


def test_format_differences_still_match():
    assert g.check("about 92 percent, i.e. the 96th percentile", [TOOL]) == []
    assert g.check("48963 departures", [TOOL]) == []           # thousands separator
    assert g.check("11.40%", [TOOL]) == []                       # trailing zero


def test_labels_and_ids_are_not_claims():
    answer = ("1. Answer [assumption: A-05] [domain: SNA-01] [data: T-100, 2025-05 to 2026-04]\n"
              "2. Summer = Q3; curfew 07:00-22:00; runways 28R/10L; growth since 2019 and 2022.")
    assert g.check(answer, [TOOL]) == []


def test_small_counts_are_exempt():
    assert g.check("Two airports, 3 flags, 10 checks.", [TOOL]) == []


def test_users_own_numbers_count_as_evidence():
    assert g.check("At your 50% threshold, nothing changes.", [TOOL, "what if the threshold is 50%?"]) == []


def test_each_unverified_number_listed_once():
    assert g.check("17% here, 17% again, and 23%.", [TOOL]) == ["17", "23"]
