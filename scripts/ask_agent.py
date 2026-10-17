"""Ask the agent questions end to end (uses the Claude API: costs money).

Run from the repo root:
  python scripts/ask_agent.py                         # the four assignment questions
  python scripts/ask_agent.py --save docs/eval_outputs q1 q3 q4   # chosen questions, saved as markdown
Each question runs in a fresh session. Prints the answer, tool calls, grounding result, tokens and cost.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import MODEL, Agent  # noqa: E402

QUESTIONS = {
    "q1": "Which airports in New England are strong candidates for terminal expansion?",
    "q2": "Compare LA and Santa Ana airport congestion levels.",
    "q3": "What is the percentage of long haul flights out of Anchorage airport?",
    "q4": "What is the unmet flight demand in SFO airport and why?",
}


def report(qid: str, question: str, turn, seconds: float) -> str:
    calls = "\n".join(f"- `{name}({json.dumps(args)})`" for name, args in turn.tool_calls) or "- none"
    grounding = "clean" if not turn.unverified_numbers else f"UNVERIFIED {turn.unverified_numbers}"
    return (f"# {qid.upper()}: {question}\n\n{turn.answer}\n\n---\n\n**Tool calls**\n\n{calls}\n\n"
            f"**Grounding check:** {grounding}  \n**Model:** {MODEL} · **Stop:** {turn.stop_reason} · "
            f"**Time:** {seconds:.0f} s · **Cost:** ${turn.cost_usd:.3f} · **Run:** {time.strftime('%Y-%m-%d')}\n")


def main(args: list[str]) -> None:
    out_dir = None
    if args[:1] == ["--save"]:
        out_dir, args = ROOT / args[1], args[2:]
        out_dir.mkdir(parents=True, exist_ok=True)
    chosen = {k: QUESTIONS[k] for k in args} if args else QUESTIONS
    total = 0.0
    for qid, q in chosen.items():
        t0 = time.time()
        turn = Agent().ask(q)
        total += turn.cost_usd
        text = report(qid, q, turn, time.time() - t0)
        print(text)
        if out_dir:
            (out_dir / f"{qid}.md").write_text(text, encoding="utf-8")
    print(f"TOTAL COST: ${total:.3f}")


if __name__ == "__main__":
    main(sys.argv[1:])
