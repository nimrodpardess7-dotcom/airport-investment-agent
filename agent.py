"""The agent: Claude picks tools and narrates; Python (tools.py) computes every number.

A manual tool-use loop, kept short on purpose so every step is visible:
  1. send the conversation + tool schemas to Claude
  2. if Claude asks for tools, run them in Python and send the results back
  3. repeat until Claude answers; then grounding.check() lists any number not found in the evidence

The history is append-only (the model's reasoning blocks must be passed back unchanged).
"""

import json
import os
from dataclasses import dataclass, field

import anthropic
from dotenv import load_dotenv

import grounding
import tools
from config import CONFIG, ROOT

load_dotenv(ROOT / ".env")

MODEL = CONFIG["llm"]["model"]
EFFORT = CONFIG["llm"]["effort"]
MAX_TOOL_ROUNDS = CONFIG["llm"]["max_tool_rounds"]
SYSTEM_PROMPT = (ROOT / "prompts" / "system.md").read_text(encoding="utf-8")
BETAS = ["server-side-fallback-2026-07-01"]   # refusal fallback: another model answers if a filter wrongly declines


# --- Tool schemas (strict: Claude's arguments always match exactly) --------------------------------

def _tool(name: str, description: str, properties: dict) -> dict:
    return {"name": name, "description": description, "strict": True,
            "input_schema": {"type": "object", "properties": properties,
                             "required": list(properties), "additionalProperties": False}}


def _nullable(schema: dict, description: str) -> dict:
    """'This schema, or null' in the form strict mode accepts (null = use the tool's default)."""
    return {"anyOf": [schema, {"type": "null"}], "description": description}


AIRPORT = {"type": "string", "description": "3-letter U.S. IATA code, e.g. BOS"}
WEIGHTS = _nullable({"type": "object", "additionalProperties": False, "required": ["growth", "pressure", "scale"],
                     "properties": {k: {"type": "number"} for k in ("growth", "pressure", "scale")}},
                    "What-if weights (relative; code normalizes). null = use the lens.")

TOOL_SCHEMAS = [
    _tool("rank_airports",
          "Rank airports by Opportunity Score (0-100) with the binding-constraint label and flags. "
          "Percentiles are national; the region/states filter is applied afterwards.",
          {"region": _nullable({"type": "string", "enum": list(CONFIG["regions"])}, "Named region, or null"),
           "states": _nullable({"type": "array", "items": {"type": "string"}},
                               "2-letter state codes, used when region is null; null = national"),
           "lens": {"type": "string", "enum": list(CONFIG["scoring"]["lenses"]),
                    "description": "absolute = default weights; pressure = scale weight 0"},
           "weights": WEIGHTS,
           "top": {"type": "integer", "description": "How many airports to return (e.g. 10)"}}),
    _tool("compare_airports",
          "Compare airports side by side: score, label, and the three kinds of congestion "
          "(demand, airfield, regulatory) with KB facts.",
          {"codes": {"type": "array", "items": AIRPORT}}),
    _tool("route_mix",
          "Share of long-haul departures from an airport over a period. The code picks the data source "
          "from the period. Periods: 'last_7_days', 'latest' (latest full year), '2025', '2025-Q3', "
          "'2025-07'. A specific day is not supported.",
          {"airport": AIRPORT,
           "period": {"type": "string"},
           "threshold_km": _nullable({"type": "number"}, "null = 4,000 km (A-05)"),
           "include_cargo": {"type": "boolean", "description": "false = passenger aircraft only"}}),
    _tool("demand_signals",
          "Unmet-demand evidence for one airport: five traces plus capacity loss per hour when documented.",
          {"airport": AIRPORT}),
    _tool("get_constraints", "Curated facts for one airport: legal caps, curfews, runway geometry, "
                             "schedule level, each with source and confidence.", {"airport": AIRPORT}),
    _tool("live_status", "Live FAA status for one airport: ground delay programs, ground stops, "
                         "delays, arrival rate.", {"airport": AIRPORT}),
    _tool("get_assumption", "Explain one assumption from the register (e.g. 'A-05'): statement, why, "
                            "alternatives, sensitivity.", {"assumption_id": {"type": "string"}}),
]

TOOL_FUNCTIONS = {
    "rank_airports": tools.rank_airports, "compare_airports": tools.compare_airports,
    "route_mix": tools.route_mix, "demand_signals": tools.demand_signals,
    "get_constraints": tools.get_constraints, "live_status": tools.live_status,
    "get_assumption": tools.get_assumption,
}


def run_tool(name: str, args: dict) -> dict:
    """Run one tool. null arguments mean 'use the tool's default'."""
    return TOOL_FUNCTIONS[name](**{k: v for k, v in args.items() if v is not None})


# --- One conversation ------------------------------------------------------------------------------

def _client() -> anthropic.Anthropic:
    """Claude client. ANTHROPIC_WORKSPACE_ID (optional, .env) is needed only for keys not scoped to a workspace."""
    workspace = os.getenv("ANTHROPIC_WORKSPACE_ID")
    return anthropic.Anthropic(default_headers={"anthropic-workspace-id": workspace} if workspace else None)



@dataclass
class Turn:
    answer: str
    tool_calls: list = field(default_factory=list)        # [(name, args)] in call order
    unverified_numbers: list = field(default_factory=list)  # filled by the grounding check
    stop_reason: str = ""
    usage: dict = field(default_factory=dict)              # tokens summed over this turn's API calls

    @property
    def cost_usd(self) -> float:
        """Estimated cost at the configured per-million-token prices (fallback-model calls not repriced)."""
        prices = CONFIG["llm"]["usd_per_million_tokens"]
        return sum(self.usage.get(k, 0) * prices[k] for k in prices) / 1e6


USAGE_FIELDS = ["input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"]


def _add_usage(total: dict, response) -> None:
    usage = getattr(response, "usage", None)
    for f in USAGE_FIELDS:
        total[f] = total.get(f, 0) + (getattr(usage, f, 0) or 0)


class Agent:
    """One chat session. Keeps the full message history (session memory) and every tool result."""

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or _client()
        self.messages: list = []
        self.evidence: list[str] = []   # tool results + user messages, whole session (grounding check)

    def _call(self):
        return self.client.beta.messages.create(
            model=MODEL, max_tokens=16000, betas=BETAS, fallbacks="default",
            output_config={"effort": EFFORT},
            cache_control={"type": "ephemeral"},   # system prompt + tools are identical every call
            system=SYSTEM_PROMPT, tools=TOOL_SCHEMAS, messages=self.messages)

    def ask(self, question: str) -> Turn:
        """Answer one question. A turn that doesn't finish normally (interrupted, API error, refusal,
        too many tool rounds) is rolled back, so the history sent next time is always valid."""
        mark = (len(self.messages), len(self.evidence))
        finished = False
        try:
            turn = self._run_turn(question)
            finished = turn.stop_reason in ("end_turn", "stop_sequence")
            return turn
        finally:
            if not finished:
                del self.messages[mark[0]:]
                del self.evidence[mark[1]:]

    def _run_turn(self, question: str) -> Turn:
        self.messages.append({"role": "user", "content": question})
        self.evidence.append(question)
        calls, usage = [], {}
        for _ in range(MAX_TOOL_ROUNDS):
            response = self._call()
            _add_usage(usage, response)
            self.messages.append({"role": "assistant", "content": response.content})  # append-only

            if response.stop_reason == "refusal":
                return Turn("I can't help with that request.", calls, stop_reason="refusal", usage=usage)
            if response.stop_reason != "tool_use":
                answer = "\n".join(b.text for b in response.content if b.type == "text").strip()
                return Turn(answer, calls, grounding.check(answer, self.evidence), response.stop_reason, usage)

            results = []
            for block in (b for b in response.content if b.type == "tool_use"):
                calls.append((block.name, block.input))
                self.evidence.append(json.dumps(block.input))   # inputs are shown to the user, so traceable
                try:
                    content, is_error = json.dumps(run_tool(block.name, block.input), ensure_ascii=False), False
                except Exception as e:  # a tool failure goes back to Claude as an error, never hidden
                    content, is_error = f"{type(e).__name__}: {e}", True
                self.evidence.append(content)
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": content, "is_error": is_error})
            self.messages.append({"role": "user", "content": results})  # all results in one message

        return Turn("I stopped after too many tool calls; please narrow the question.", calls,
                    stop_reason="max_tool_rounds", usage=usage)
