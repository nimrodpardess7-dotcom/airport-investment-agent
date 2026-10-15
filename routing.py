"""Deterministic period -> data source routing.

last 7 days -> OpenSky; month/season/year -> TranStats route-level (if available) else T-100 summary
approximation; specific past day or anything uncovered -> unsupported + nearest supported period.
The LLM never chooses the source.
"""
