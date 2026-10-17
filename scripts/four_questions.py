"""Answer the four assignment questions by calling the tools directly (no LLM).

Run from the repo root:  python scripts/four_questions.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools  # noqa: E402


def show(title: str, result: dict) -> None:
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    show("Q1a. New England terminal candidates (absolute lens)", tools.rank_airports(region="new_england", top=6))
    show("Q1b. New England terminal candidates (pressure lens)",
         tools.rank_airports(region="new_england", lens="pressure", top=6))
    show("Q2. LAX vs SNA: congestion", tools.compare_airports(["LAX", "SNA"]))
    show("Q3. % long-haul departures from ANC (latest full year)", tools.route_mix("ANC", "latest"))
    show("Q4. SFO unmet demand and why", tools.demand_signals("SFO"))
