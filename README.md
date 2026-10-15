# airport-investment-agent

AI agent for airport terminal investment analysis: live aviation data, deterministic scoring, transparent reasoning.

Python computes every number; the LLM only narrates, tagging each claim as `[data]`, `[domain]` or `[assumption]`.

> Status: scaffold only (Phase -1). See [docs/PLAN.md](docs/PLAN.md) for the spec and phases.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate   # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # then fill in the keys
```

## Layout

| Path | Purpose |
|---|---|
| `sources/` | API clients (BTS T-100, FAA NAS Status, OpenSky, OurAirports) + TTL cache |
| `metrics.py`, `scoring.py` | Metrics, Opportunity Score, Binding Constraint label |
| `routing.py` | Deterministic period → data source |
| `tools.py`, `agent.py` | Agent tools and Claude tool-calling loop with grounding check |
| `app.py` | Streamlit chat |
| `config.yaml` | Weights and thresholds |
| `kb/` | `constraints.yaml` (facts), `assumptions.yaml` (judgment calls) |
| `tests/` | Unit and golden tests |
