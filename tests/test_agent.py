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
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


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
    assert "A-05" in json.loads(a.evidence[-1])["values"]["id"]  # [question, tool input, tool result]
    assert turn.unverified_numbers == []                          # 4,000 is in the tool result


def test_invented_number_is_flagged_on_the_turn():
    fake = FakeClient([
        NS(stop_reason="tool_use", content=[tool_use("get_assumption", {"assumption_id": "A-05"})]),
        NS(stop_reason="end_turn", content=[text("Long-haul means over 5,500 km.")]),
    ])
    assert agent.Agent(client=fake).ask("?").unverified_numbers == ["5,500"]
    # Every request carries the stable prefix and the agreed settings.
    for r in fake.requests:
        assert r["fallbacks"] == "default" and r["cache_control"] == {"type": "ephemeral"}
        assert r["output_config"] == {"effort": agent.EFFORT}


def test_numbers_from_tool_inputs_are_traceable():
    # Live run: the agent wrote "your 0.70 / 0.35 / 0.30", the weights it passed in. Not invented.
    fake = FakeClient([
        NS(stop_reason="tool_use", content=[tool_use("rank_airports", {
            "region": "new_england", "states": None, "lens": "absolute",
            "weights": {"growth": 0.70, "pressure": 0.35, "scale": 0.30}, "top": 5})]),
        NS(stop_reason="end_turn", content=[text("Your 0.70 / 0.35 / 0.30 weights were normalized.")]),
    ])
    assert agent.Agent(client=fake).ask("growth twice as much?").unverified_numbers == []


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


class Interrupt(Exception):
    """Stands in for a Streamlit rerun or an API error in the middle of a turn."""


def test_interrupted_turn_is_rolled_back_and_chat_continues():
    # The reported bug: a click mid-answer left a tool request without its result -> every later call 400'd.
    responses = [
        NS(stop_reason="end_turn", content=[text("First answer.")]),
        NS(stop_reason="tool_use", content=[tool_use("get_assumption", {"assumption_id": "A-05"})]),
        Interrupt("click while answering"),
        NS(stop_reason="end_turn", content=[text("Third answer.")]),
    ]
    a = agent.Agent(client=FakeClient(responses))
    a.ask("first")
    before = (list(a.messages), list(a.evidence))
    try:
        a.ask("second")
    except Interrupt:
        pass
    assert (a.messages, a.evidence) == before                  # half-finished turn removed
    assert a.ask("third").answer == "Third answer."             # conversation continues
    roles = [m["role"] for m in a.messages]
    assert roles == ["user", "assistant", "user", "assistant"]  # valid history: no orphan tool request


def test_refused_or_runaway_turns_leave_no_trace():
    fake = FakeClient([NS(stop_reason="refusal", content=[])])
    a = agent.Agent(client=fake)
    a.ask("?")
    assert a.messages == [] and a.evidence == []


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
