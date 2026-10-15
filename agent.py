"""Claude tool-calling loop, system prompt and grounding check.

The grounding check extracts every number from the final answer and verifies it appears in
that turn's tool results; unmatched numbers are flagged.
"""
