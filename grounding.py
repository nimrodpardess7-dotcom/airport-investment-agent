"""Grounding check: every number in the answer must come from a tool result (or the user's own words).

Pure code, no LLM. Numbers are compared by value, so "92%", "92 percent" and "p92" all match a tool's 92.
Not checked (they are labels, not claims):
  - years (1990-2039), dates ("2025-05") and clock times ("07:00")
  - IDs: assumption and KB ids ("A-05", "SNA-01"), quarters ("Q3"), runway names ("28R")
  - list markers at the start of a line ("1.") and small counts (0-10)
Anything else that can't be found is returned as unverified, and shown under the answer.
"""

import re

SKIP = [
    r"\b\d{4}-\d{2}(?:-\d{2})?\b",         # dates: 2025-05, 2024-03-03
    r"\b\d{1,2}:\d{2}\b",                  # times: 07:00
    r"\b[A-Za-z]{1,4}-\d+[a-z]?\b",        # ids: A-05, SNA-01, LAX-02 (a letter suffix is allowed)
    r"\b[A-OQ-Za-oq-z]\d+\b",              # letter-prefixed labels: Q3, (but not p96 percentiles)
    r"\b\d+[LRC]\b",                       # runway names: 28R, 1L
    r"(?m)^\s*\d+\.\s",                    # list markers: "1. "
]
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _strip(text: str) -> str:
    for pattern in SKIP:
        text = re.sub(pattern, " ", text)
    return text


def _value(token: str) -> str:
    """Canonical value: no thousands separators, no trailing zeros. '1,500' -> '1500', '82.10' -> '82.1'."""
    v = token.replace(",", "")
    return v.rstrip("0").rstrip(".") if "." in v else v


def numbers(text: str) -> list[str]:
    """The numbers a reader would see as claims, in order."""
    return NUMBER.findall(_strip(text))


def _is_exempt(token: str) -> bool:
    v = _value(token)
    if "." not in v and v.isdigit():
        n = int(v)
        return n <= 10 or 1990 <= n <= 2039   # small counts and years
    return False


def check(answer: str, evidence: list[str]) -> list[str]:
    """Return the numbers in `answer` that appear nowhere in `evidence` (tool results + user messages)."""
    known = {_value(t) for text in evidence for t in numbers(text)}
    unverified = []
    for token in numbers(answer):
        if not _is_exempt(token) and _value(token) not in known and token not in unverified:
            unverified.append(token)
    return unverified
