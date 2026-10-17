# Airport Investment Agent

A chat agent that answers: **where would new U.S. passenger-terminal capacity pay off, and what blocks it?**

Python computes every number from live public data (deterministic score + binding-constraint label). Claude picks the tools and explains the results. A grounding check flags any number in an answer that no tool produced.

**Example:** *"Compare LAX and Santa Ana"* → Santa Ana is **Regulatory** (92% of its 12.2M legal cap); LAX has no binding constraint (traffic still below 2019).

## Setup

```bash
python -m venv .venv && .venv/Scripts/activate     # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                # add ANTHROPIC_API_KEY (OpenSky keys optional)
```

## Run

```bash
streamlit run app.py              # chat
python -m pytest                  # 74 tests
python scripts/run_eval.py        # 8-case eval through Claude (~$0.40)
```

## Docs

- [docs/DESIGN.md](docs/DESIGN.md): scoring, tradeoffs, where AI is used, limits
- [config.yaml](config.yaml) · [kb/](kb/): weights, sourced facts, assumptions (all editable)

Data: BTS T-100 and TranStats, FAA NAS Status, OurAirports, OpenSky (non-commercial).
