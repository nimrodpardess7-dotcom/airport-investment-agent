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


def constraint_label(row: pd.Series) -> tuple[str, list[str]]:
    """Return (label, reasons). Rules in order: Regulatory, Airfield, Terminal, None evident."""
    airport = row.name

    # Regulatory (A-12): a hard passenger cap, and total passengers (A-07) at >= 85% of it.
    for cap in _constraints(airport, "cap"):
        limit = cap["value"].get("annual_passengers")
        if cap["value"].get("hard") and limit:
            total = row["passengers"] * CONFIG["passengers_per_enplanement"]
            if total / limit >= LABEL_CFG["regulatory_utilization"]:
                return "Regulatory", [f"passengers at {total / limit:.0%} of the {limit / 1e6:.1f}M legal cap [{cap['id']}]"]

    # Airfield (A-14): measured runway/ATC delays, or a documented runway-geometry fact.
    reasons = []
    if row["pct_nas_share"] >= LABEL_CFG["airfield_percentile"]:
        reasons.append(f"runway/ATC (NAS) delay share at p{row['pct_nas_share']:.0f} of peers")
    for rw in _constraints(airport, "runway"):
        if rw["value"].get("geometry"):
            reasons.append(f"runway geometry: {rw['value']['geometry'].replace('_', ' ')} [{rw['id']}]")
    if reasons:
        return "Airfield", reasons

    # Terminal (A-13): demand is growing and pressing, and nothing above blocks it.
    bar = LABEL_CFG["terminal_percentile"]
    if row["growth"] >= bar and row["pressure"] >= bar:
        return "Terminal", [f"growth p{row['growth']:.0f} and pressure p{row['pressure']:.0f}, both >= p{bar}"]

    return "None evident", ["demand is not yet pressing on capacity"]


def upgauging_signature(row: pd.Series) -> bool:
    """A-09 (display-only): bigger planes than peers while flights grew less than peers."""
    sig = LABEL_CFG["upgauging_signature"]
    return bool(row["pct_upgauging"] >= sig["upgauging_min_percentile"]
                and row["pct_departures_change"] <= sig["departures_change_max_percentile"])


# --- 5. Flags (shown next to the score, never inside it) -----------------------------------------

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
    return out


# --- 6. Everything together ----------------------------------------------------------------------

def evaluate(table: pd.DataFrame, weights: dict | None = None, lens: str | None = None) -> pd.DataFrame:
    """Score every airport nationally, then add label, reasons, flags and the A-09 display.

    Region filtering happens after this, so percentiles always come from the national peer group.
    """
    out = score(table, weights or lens_weights(lens or SCORE_CFG["default_lens"]))
    labels = out.apply(constraint_label, axis=1)
    out["label"] = labels.str[0]
    out["label_reasons"] = labels.str[1]
    out["flags"] = out.apply(flags, axis=1)
    out["upgauging_signature"] = out.apply(upgauging_signature, axis=1)
    return out.sort_values("score", ascending=False)


def rank(table: pd.DataFrame, states: list[str] | None = None, **kwargs) -> pd.DataFrame:
    """National evaluation, then filter to `states` (e.g. New England)."""
    out = evaluate(table, **kwargs)
    return out[out["state"].isin(states)] if states else out
