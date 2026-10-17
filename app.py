"""Streamlit chat with the airport investment agent.

Run:  streamlit run app.py
One Agent per browser session gives the chat its memory (follow-ups, what-if weights).
Under each answer, "How this answer was built" shows the tool calls, the grounding check, time and cost.
"""

import time

import anthropic
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
    st.session_state.history = []   # [{"role", "content", "turn", "seconds"}]


def ask_example(question: str) -> None:
    st.session_state.pending = question


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

# --- Sidebar ---------------------------------------------------------------------------------------
with st.sidebar:
    st.title("✈️ Airport Investment Agent")
    st.caption("Where would new U.S. passenger-terminal capacity pay off, and what blocks it?")

    st.subheader("Try a question")
    for label, question in EXAMPLES.items():
        st.button(label, on_click=ask_example, args=(question,), width="stretch")

    st.subheader("Data windows")
    with st.spinner("Loading data…"):
        meta = tools._table()[1]
    for key in ("score_window", "nas_window", "freighter_window"):
        st.caption(meta[key])
    st.caption(f"{meta['airports_in_universe']} U.S. airports scored · live FAA status · OpenSky (last 7 days)")

    st.divider()
    st.button("New conversation", on_click=new_conversation, width="stretch")
    st.caption("Python computes every number; Claude explains it. Each claim is tagged "
               "[data], [domain] or [assumption]. Scores are deterministic and reproducible.")

# --- Chat ------------------------------------------------------------------------------------------
st.header("Ask about U.S. airport terminal investment")

for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        show_markdown(msg["content"])
        if msg.get("turn"):
            show_trust_panel(msg["turn"], msg["seconds"])

question = st.chat_input("e.g. Which New England airports should we invest in?") or st.session_state.pop("pending", None)
if question:
    st.session_state.history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        show_markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Calling tools and checking every number…"):
            t0 = time.time()
            try:
                turn = st.session_state.agent.ask(question)
            except anthropic.APIError as e:
                st.error(f"The Claude API returned an error ({type(e).__name__}). Please try again.")
                st.stop()
        seconds = time.time() - t0
        show_markdown(turn.answer)
        show_trust_panel(turn, seconds)
    st.session_state.history.append({"role": "assistant", "content": turn.answer, "turn": turn, "seconds": seconds})
