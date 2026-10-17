"""Run the end-to-end eval (tests/eval_questions.yaml) through the real agent and grade it in code.

Run from the repo root:  python scripts/run_eval.py
Uses the Claude API (about $0.40). Writes docs/eval_results.md and exits non-zero if any case fails.
"""

import re
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import MODEL, Agent  # noqa: E402


def grade(case: dict, turn) -> list[str]:
    """Return the failed checks for one case (empty = pass)."""
    called = {name for name, _ in turn.tool_calls}
    failures = [f"tool not called: {t}" for t in case.get("tools", []) if t not in called]
    if case.get("no_tools") and called:
        failures.append(f"should ask, not call tools: {sorted(called)}")
    failures += [f"missing: /{p}/" for p in case.get("must_include", [])
                 if not re.search(p, turn.answer, re.IGNORECASE)]
    if turn.unverified_numbers:
        failures.append(f"unverified numbers: {turn.unverified_numbers}")
    if turn.stop_reason not in ("end_turn", "stop_sequence"):
        failures.append(f"stop reason: {turn.stop_reason}")
    return failures


def main() -> int:
    cases = yaml.safe_load((ROOT / "tests" / "eval_questions.yaml").read_text(encoding="utf-8"))
    rows, total_cost = [], 0.0
    for case in cases:
        agent, t0 = Agent(), time.time()
        for question in case["turns"]:
            turn = agent.ask(question)
            total_cost += turn.cost_usd
        failures = grade(case, turn)
        rows.append((case["id"], not failures, [n for n, _ in turn.tool_calls], failures, time.time() - t0))
        print(f"{'PASS' if not failures else 'FAIL'}  {case['id']:<22} tools={[n for n, _ in turn.tool_calls]} "
              f"{failures or ''}")
        print(f"      answer: {turn.answer[:220].replace(chr(10), ' ')}…\n")

    passed = sum(ok for _, ok, *_ in rows)
    lines = [f"# Eval results\n",
             f"{passed}/{len(rows)} cases passed · total cost ${total_cost:.2f} · model {MODEL} · "
             f"run {time.strftime('%Y-%m-%d')}\n",
             "Graded in code: required tools called, required facts/caveats present (regex), clean grounding check.\n",
             "| Case | Result | Tools called (last turn) | Failed checks | Time |", "|---|---|---|---|---|"]
    for case_id, ok, tools_called, failures, seconds in rows:
        lines.append(f"| {case_id} | {'✅ pass' if ok else '❌ fail'} | {', '.join(tools_called) or 'none'} | "
                     f"{'; '.join(failures) or '-'} | {seconds:.0f} s |")
    (ROOT / "docs" / "eval_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{passed}/{len(rows)} passed · total cost ${total_cost:.3f} · written to docs/eval_results.md")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
