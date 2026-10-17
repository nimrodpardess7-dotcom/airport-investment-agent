"""Deterministic scoring: Opportunity Score, Binding Constraint label, flags. No LLM, no network.

Input: the airport table from dataset.build() (one row per airport). Every threshold comes from
config.yaml (with its A-ID); every fact comes from kb/constraints.yaml.
"""

import math

import pandas as pd

from config import CONFIG, CONSTRAINTS

SCORE_CFG, LABEL_CFG, FLAG_CFG = CONFIG["scoring"], CONFIG["constraint_label"], CONFIG["flags"]

# Each score component is the mean of these metric percentiles (PLAN section 3).
COMPONENTS = {
    "growth": ["growth_vs_2019", "cagr_since_2022"],
    "pressure": ["load_factor", "upgauging"],
    "scale": ["passengers"],
}
# Size is absolute, so Scale is ranked against ALL airports. Growth and pressure are ranked within the
# peer group, because +5% means different things at BOS and Burlington.
RANKED_NATIONALLY = {"passengers"}
# Also ranked within the peer group: NAS share feeds the label; the other two are display-only evidence.
EVIDENCE = ["nas_share", "departures_per_runway", "departures_change"]


# --- 1. Percentiles ------------------------------------------------------------------------------

def percentile(values: pd.Series, groups: pd.Series) -> pd.Series:
    """0-100 rank percentile within each group. Missing values stay missing."""
    return values.groupby(groups).rank(pct=True) * 100


# --- 2. Weights ----------------------------------------------------------------------------------

def lens_weights(lens: str) -> dict:
    return dict(SCORE_CFG["lenses"][lens])


def validate_weights(weights: dict) -> dict:
    """What-if weights from chat: exactly the three components, non-negative, normalized to sum to 1."""
    if set(weights) != set(COMPONENTS):
        raise ValueError(f"weights must be exactly {sorted(COMPONENTS)}")
    if any(v < 0 for v in weights.values()):
        raise ValueError("weights must be non-negative")
    total = sum(weights.values())
    if total == 0:
        raise ValueError("weights must not all be zero")
    return {k: v / total for k, v in weights.items()}


# --- 3. Score ------------------------------------------------------------------------------------

def score(table: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """Add percentile columns, the three components (0-100) and the weighted score."""
    weights = validate_weights(weights)
    out = table.copy()
    national = pd.Series("all", index=out.index)
    for col in [c for cols in COMPONENTS.values() for c in cols] + EVIDENCE:
        group = national if col in RANKED_NATIONALLY else out["hub_class"]
        out[f"pct_{col}"] = percentile(out[col], group)

    for comp, cols in COMPONENTS.items():
        out[comp] = out[[f"pct_{c}" for c in cols]].mean(axis=1, skipna=False)

    # A-19: too many missing months -> components n/a (and so the score is n/a).
    too_sparse = out["missing_months"] >= FLAG_CFG["completeness"]["skip_component_if_missing_months"]
    out.loc[too_sparse, list(COMPONENTS)] = math.nan

    out["score"] = sum(w * out[c] for c, w in weights.items())
    return out


# --- 4. Binding Constraint label (first match wins) ----------------------------------------------

def _constraints(airport: str, kind: str) -> list[dict]:
    return [c for c in CONSTRAINTS if c["airport"] == airport and c["type"] == kind]


def _check(rule: str, metric: str, value: str, percentile: str, threshold: str, passed: bool) -> dict:
    """One label condition, with everything needed to explain it ("display" is the plain sentence)."""
    if value == "n/a":
        sentence = f"{rule}: {metric} has no data, so this check can't pass"
    else:
        shown = value if percentile in ("n/a", value) else f"{value} ({percentile})"
        sentence = f"{rule}: {metric} {shown} {'meets' if passed else 'misses'} the {threshold} bar"
    return {"rule": rule, "metric": metric, "value": value, "percentile": percentile, "threshold": threshold,
            "passed": bool(passed), "display": sentence}


def _pct(x) -> str:
    return "n/a" if pd.isna(x) else f"p{x:.0f}"


def constraint_label(row: pd.Series) -> tuple[str, list[dict], list[str]]:
    """Return (label, checks, near_misses). Rules in order: Regulatory, Airfield, Terminal, None evident.

    `checks` lists every condition evaluated up to the rule that fired, passed or not, so the answer can
    say exactly what triggered the label and what didn't. `near_misses` lists checks within A-21 points.
    """
    airport, checks, near = row.name, [], []
    band = LABEL_CFG["near_miss_points"]

    def near_miss(metric: str, value: float, bar: float, unit: str) -> None:
        if pd.notna(value) and abs(value - bar) <= band:
            near.append(f"{metric} {value:.0f}{unit} is within {band} points of the {bar:.0f}{unit} bar")

    # Regulatory (A-12): a hard passenger cap, and total passengers (A-07) at >= 85% of it.
    for cap in _constraints(airport, "cap"):
        limit = cap["value"].get("annual_passengers")
        if cap["value"].get("hard") and limit:
            used = row["passengers"] * CONFIG["passengers_per_enplanement"] / limit
            bar = LABEL_CFG["regulatory_utilization"]
            checks.append(_check("Regulatory", f"passengers vs the {limit / 1e6:.1f}M legal cap [{cap['id']}]",
                                 f"{used:.0%}", "n/a", f">= {bar:.0%}", used >= bar))
            near_miss("cap utilization", used * 100, bar * 100, "%")
            if used >= bar:
                return "Regulatory", checks, near

    # Airfield (A-14): measured runway/ATC delays, or a documented runway-geometry fact.
    bar = LABEL_CFG["airfield_percentile"]
    nas_ok = row["pct_nas_share"] >= bar
    checks.append(_check("Airfield", "runway/ATC (NAS) delay share",
                         "n/a" if pd.isna(row["nas_share"]) else f"{row['nas_share']:.1%}",
                         _pct(row["pct_nas_share"]), f">= p{bar}", nas_ok))
    near_miss("NAS delay share", row["pct_nas_share"], bar, "th percentile")
    geometry = [rw for rw in _constraints(airport, "runway") if rw["value"].get("geometry")]
    for rw in geometry:
        checks.append(_check("Airfield", f"runway geometry [{rw['id']}]", rw["value"]["geometry"].replace("_", " "),
                             "n/a", "documented", True))
    if nas_ok or geometry:
        return "Airfield", checks, near

    # Terminal (A-13): demand is growing and pressing, and nothing above blocks it.
    bar = LABEL_CFG["terminal_percentile"]
    for comp in ("growth", "pressure"):
        checks.append(_check("Terminal", comp, _pct(row[comp]), _pct(row[comp]), f">= p{bar}", row[comp] >= bar))
        near_miss(comp, row[comp], bar, "th percentile")
    if row["growth"] >= bar and row["pressure"] >= bar:
        return "Terminal", checks, near

    return "None evident", checks, near


def upgauging_signature(row: pd.Series) -> bool:
    """A-09 (display-only): bigger planes than peers while flights grew less than peers."""
    sig = LABEL_CFG["upgauging_signature"]
    return bool(row["pct_upgauging"] >= sig["upgauging_min_percentile"]
                and row["pct_departures_change"] <= sig["departures_change_max_percentile"])


# --- 5. Flags (shown next to the score, never inside it) -----------------------------------------

# Each data-dependent flag check and the column it needs. A check whose input is missing didn't run.
FLAG_INPUTS = {"seasonality": "seasonality", "cargo-heavy": "freighter_share",
               "carrier concentration": "top_carrier_share", "ultra-low-cost share": "ulcc_share",
               "low base": "passengers_2019"}


def flags(row: pd.Series) -> list[str]:
    out = []
    if row["hub_class"] == "non-hub":
        out.append("low confidence: non-hub airport")
    if row["borderline_class"]:
        out.append(f"borderline peer group: near a hub-class cutoff (counted as {row['hub_class']})")
    if row["seasonality"] >= FLAG_CFG["seasonality_ratio_threshold"]:
        out.append(f"low confidence: highly seasonal (busiest/quietest month = {row['seasonality']:.1f})")
    if row["missing_months"] >= FLAG_CFG["completeness"]["low_confidence_if_missing_months"]:
        out.append(f"low confidence: {row['missing_months']:.0f} missing month(s) in a required window")
    if row["freighter_share"] >= FLAG_CFG["cargo_heavy_freighter_share"]:
        out.append(f"cargo-heavy: freighters are {row['freighter_share']:.0%} of departures")
    if row["top_carrier_share"] >= FLAG_CFG["top_carrier_share_threshold"]:            # A-22
        out.append(f"carrier concentration: one airline ({row['top_carrier']}) has "
                   f"{row['top_carrier_share']:.0%} of seats")
    if row["ulcc_share"] >= FLAG_CFG["ulcc_share_threshold"]:                          # A-11
        out.append(f"ultra-low-cost carriers have {row['ulcc_share']:.0%} of seats "
                   "(they fill planes by design, which inflates pressure)")
    low = FLAG_CFG["low_base"]                                                          # A-23
    if row["pct_growth_vs_2019"] >= low["growth_min_percentile"] and row["passengers_2019"] < low["max_boardings_2019"]:
        out.append(f"low base: growth {_pct(row['pct_growth_vs_2019'])} from only "
                   f"{row['passengers_2019']:,.0f} boardings in 2019")
    return out


def flag_checks_not_run(row: pd.Series) -> list[str]:
    """Flag checks that couldn't run for this airport because their input is missing."""
    return [name for name, col in FLAG_INPUTS.items() if pd.isna(row[col])]


# --- 6. Everything together ----------------------------------------------------------------------

def evaluate(table: pd.DataFrame, weights: dict | None = None, lens: str | None = None) -> pd.DataFrame:
    """Score every airport nationally, then add label, evidence, near misses, flags and the A-09 display.

    Region filtering happens after this, so percentiles always come from the national peer group.
    """
    out = score(table, weights or lens_weights(lens or SCORE_CFG["default_lens"]))
    labels = out.apply(constraint_label, axis=1)
    out["label"] = labels.str[0]
    out["label_evidence"] = labels.str[1]
    out["near_misses"] = labels.str[2]
    out["flags"] = out.apply(flags, axis=1)
    out["flag_checks_not_run"] = out.apply(flag_checks_not_run, axis=1)
    out["upgauging_signature"] = out.apply(upgauging_signature, axis=1)
    return out.sort_values("score", ascending=False)


def rank(table: pd.DataFrame, states: list[str] | None = None, **kwargs) -> pd.DataFrame:
    """National evaluation, then filter to `states` (e.g. New England)."""
    out = evaluate(table, **kwargs)
    return out[out["state"].isin(states)] if states else out
