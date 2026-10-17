"""Ask the agent the four assignment questions end to end (uses the Claude API: costs money).

Run from the repo root:  python scripts/ask_agent.py
Each question runs in a fresh session. Prints the answer, tool calls, grounding result, tokens and cost.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import Agent  # noqa: E402

QUESTIONS = [
    "Which airports in New England are the best candidates for new terminal investment?",
    "Compare congestion at LAX and Santa Ana. What kind of constraint does each face?",
    "What percentage of flights out of Anchorage are long-haul?",
    "SFO seems to have unmet demand. How much, and why?",
]


def main(questions: list[str]) -> None:
    total = 0.0
    for i, q in enumerate(questions, 1):
        t0 = time.time()
        turn = Agent().ask(q)
        total += turn.cost_usd
        print(f"\n{'=' * 100}\nQ{i}. {q}\n{'=' * 100}\n")
        print(turn.answer)
        print(f"\n--- tool calls ({len(turn.tool_calls)}):")
        for name, args in turn.tool_calls:
            print(f"    {name}({json.dumps(args)})")
        print(f"--- grounding: {'clean' if not turn.unverified_numbers else 'UNVERIFIED ' + str(turn.unverified_numbers)}")
        print(f"--- stop: {turn.stop_reason} | {time.time() - t0:.0f}s | tokens {turn.usage} | cost ${turn.cost_usd:.3f}")
    print(f"\nTOTAL COST: ${total:.3f}")


if __name__ == "__main__":
    main(sys.argv[1:] or QUESTIONS)
