"""Offline tests for agent.py: a fake Claude client drives the loop, so no API calls and no cost."""

import json
from types import SimpleNamespace as NS

import agent


def text(t):
    return NS(type="text", text=t)


def tool_use(name, args, id_="tu_1"):
    return NS(type="tool_use", name=name, input=args, id=id_)


class FakeClient:
    """Returns scripted responses in order and records every request."""

    def __init__(self, responses):
        self.responses, self.requests = list(responses), []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


def test_schemas_are_strict_and_complete():
    names = {t["name"] for t in agent.TOOL_SCHEMAS}
    assert names == set(agent.TOOL_FUNCTIONS)
    for t in agent.TOOL_SCHEMAS:
        s = t["input_schema"]
        assert t["strict"] and s["additionalProperties"] is False
        assert set(s["required"]) == set(s["properties"])


def test_loop_runs_tool_then_answers():
    fake = FakeClient([
        NS(stop_reason="tool_use", content=[tool_use("get_assumption", {"assumption_id": "A-05"})]),
        NS(stop_reason="end_turn", content=[text("Long-haul means over 4,000 km [assumption: A-05].")]),
    ])
    a = agent.Agent(client=fake)
    turn = a.ask("What does long-haul mean?")
    assert turn.answer.startswith("Long-haul means")
    assert turn.tool_calls == [("get_assumption", {"assumption_id": "A-05"})]
    # The tool result went back to Claude in one user message, and was kept as evidence.
    result_msg = fake.requests[1]["messages"][-1]
    assert result_msg["role"] == "user" and result_msg["content"][0]["tool_use_id"] == "tu_1"
    assert "A-05" in json.loads(a.tool_results[0])["values"]["id"]
    # Every request carries the stable prefix and the agreed settings.
    for r in fake.requests:
        assert r["fallbacks"] == "default" and r["cache_control"] == {"type": "ephemeral"}
        assert r["output_config"] == {"effort": agent.EFFORT}


def test_tool_error_is_reported_not_hidden():
    fake = FakeClient([
        NS(stop_reason="tool_use", content=[tool_use("get_assumption", {"wrong_arg": "x"})]),
        NS(stop_reason="end_turn", content=[text("That lookup failed.")]),
    ])
    agent.Agent(client=fake).ask("?")
    result = fake.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "TypeError" in result["content"]


def test_refusal_and_round_limit():
    fake = FakeClient([NS(stop_reason="refusal", content=[])])
    assert agent.Agent(client=fake).ask("?").stop_reason == "refusal"

    loop = [NS(stop_reason="tool_use", content=[tool_use("get_assumption", {"assumption_id": "A-01"})])]
    fake = FakeClient(loop * agent.MAX_TOOL_ROUNDS)
    assert agent.Agent(client=fake).ask("?").stop_reason == "max_tool_rounds"


def test_history_is_append_only_across_turns():
    fake = FakeClient([NS(stop_reason="end_turn", content=[text("Hi.")]),
                       NS(stop_reason="end_turn", content=[text("Again.")])])
    a = agent.Agent(client=fake)
    a.ask("first")
    first = list(a.messages)
    a.ask("second")
    assert a.messages[:len(first)] == first and len(a.messages) == 4


def test_null_arguments_use_tool_defaults():
    # route_mix with threshold_km=None must fall back to A-05's 4,000 km.
    res = agent.run_tool("route_mix", {"airport": "ANC", "period": "latest", "threshold_km": None,
                                       "include_cargo": False})
    assert any("4,000 km" in c for c in res["caveats"])
