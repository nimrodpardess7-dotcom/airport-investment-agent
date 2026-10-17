"""Streamlit chat with the airport investment agent.

Run:  streamlit run app.py
One Agent per browser session gives the chat its memory (follow-ups, what-if weights).
Under each answer, "How this answer was built" shows the tool calls, the grounding check, time and cost.
"""

import time

import anthropic
import pandas as pd
import streamlit as st

import grounding
import tools
from agent import Agent

st.set_page_config(page_title="Airport Investment Agent", page_icon="✈️", layout="wide")

EXAMPLES = {
    "New England terminal candidates": "Which airports in New England are the best candidates for new terminal investment?",
    "LAX vs Santa Ana congestion": "Compare congestion at LAX and Santa Ana. What kind of constraint does each face?",
    "Anchorage long-haul share": "What percentage of flights out of Anchorage are long-haul?",
    "SFO unmet demand": "SFO seems to have unmet demand. How much, and why?",
}


def new_conversation() -> None:
    st.session_state.agent = Agent()
    st.session_state.history = []     # [{"role", "content", "turn", "seconds", "error"}]
    st.session_state.pending = None   # the question being answered; while set, every control is disabled


def ask(question: str) -> None:
    """Queue a question (from a button or the chat box). Ignored if one is already being answered."""
    if question and question.strip() and st.session_state.pending is None:
        st.session_state.pending = question.strip()


def submit_chat() -> None:
    ask(st.session_state.chat_box)


def show_markdown(text: str) -> None:
    st.markdown(text.replace("$", r"\$"))   # "$" would otherwise start a LaTeX formula


def show_trust_panel(turn, seconds: float) -> None:
    with st.expander("How this answer was built"):
        if turn.tool_calls:
            st.markdown("**Tools called (Python computed every number):**")
            for name, args in turn.tool_calls:
                shown = {k: v for k, v in args.items() if v is not None}
                st.code(f"{name}({', '.join(f'{k}={v!r}' for k, v in shown.items())})", language="python",
                        wrap_lines=True)
        else:
            st.markdown("**No tools called.**")
        if turn.unverified_numbers:
            st.warning("Numbers not found in any tool result: " + ", ".join(turn.unverified_numbers))
        elif not grounding.numbers(turn.answer):
            st.info("Grounding check: this answer contains no numbers to check.")
        else:
            st.success("Grounding check: every number in this answer was traced to a tool result.")
        st.caption(f"{seconds:.0f} s · ${turn.cost_usd:.3f} · stop: {turn.stop_reason}")


if "agent" not in st.session_state:
    new_conversation()
busy = st.session_state.pending is not None


def month(ym: str) -> str:
    return pd.Period(ym, "M").strftime("%b %Y")   # "2025-05" -> "May 2025"


# --- Sidebar ---------------------------------------------------------------------------------------
with st.sidebar:
    st.title("✈️ Airport Investment Agent")
    st.write("Find U.S. airports where new terminal capacity would pay off, and see what blocks growth.")
    st.button("New conversation", on_click=new_conversation, width="stretch", disabled=busy)

    st.subheader("Try a question")
    for label, question in EXAMPLES.items():
        st.button(label, on_click=ask, args=(question,), width="stretch", disabled=busy)

    st.subheader("Data used")
    with st.spinner("Loading data…"):
        meta = tools._table()[1]
    (s, e), (ns, ne) = meta["score_period"], meta["nas_period"]
    st.caption("The same data behind every answer:")
    st.markdown(
        f"- **Traffic and scores:** {month(s)} – {month(e)}, compared with 2019 and 2022\n"
        f"- **Delay causes:** {month(ns)} – {month(ne)}\n"
        f"- **Passenger vs cargo flights:** {meta['freighter_year']}\n"
        f"- **Live:** FAA delays right now; flights in the last 7 days\n"
        f"- **{meta['airports_in_universe']} U.S. airports** scored")
    st.caption("Sources: U.S. DOT (BTS), FAA, OpenSky Network, OurAirports")

    with st.expander("How it works"):
        st.markdown(
            "- **Python computes every number**; Claude picks the tools and explains the results.\n"
            "- **Every answer is checked:** each number must come from the data, or it is flagged.\n"
            "- **Tags show where a claim comes from:** `[data]` = live data, `[domain]` = a sourced fact, "
            "`[assumption]` = a judgment call you can question.")

# --- Chat ------------------------------------------------------------------------------------------
st.header("Ask about U.S. airport terminal investment")

for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        if msg.get("error"):
            st.error(msg["content"])
        else:
            show_markdown(msg["content"])
        if msg.get("turn"):
            show_trust_panel(msg["turn"], msg["seconds"])

st.chat_input("Answering…" if busy else "e.g. Which New England airports should we invest in?",
              key="chat_box", on_submit=submit_chat, disabled=busy)

# Answer the queued question. Controls above are already disabled, so a click can't interrupt it.
# If something still interrupts the run, Agent.ask rolls the turn back and `finally` unlocks the UI.
if busy:
    question = st.session_state.pending
    with st.chat_message("user"):
        show_markdown(question)
    try:
        with st.chat_message("assistant"), st.spinner("Calling tools and checking every number…"):
            t0 = time.time()
            try:
                turn = st.session_state.agent.ask(question)
                reply = {"role": "assistant", "content": turn.answer, "turn": turn, "seconds": time.time() - t0}
            except anthropic.APIError as e:
                reply = {"role": "assistant", "error": True,
                         "content": f"The Claude API returned an error ({type(e).__name__}). "
                                    "Nothing was lost; please ask again."}
        st.session_state.history += [{"role": "user", "content": question}, reply]
    finally:
        st.session_state.pending = None
    st.rerun()   # redraw with the controls enabled again
