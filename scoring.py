"""Opportunity Score and Binding Constraint label.

- percentile within national FAA hub-class peer group
- score_airport / rank_airports with lens (absolute | pressure) and validated what-if weights
- constraint_label: Regulatory -> Airfield -> Terminal -> None evident (first match wins)

Weights and thresholds come from config.yaml, never hard-coded.
"""
