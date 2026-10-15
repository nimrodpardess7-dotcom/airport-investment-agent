# CLAUDE.md

Airport Investment Intelligence Agent. Full spec: `docs/PLAN.md` (single source of truth; this file condenses sections 2–8 and 12).

**Thesis:** a terminal pays back per passenger. Good opportunity = many passengers + growing demand + demand pressing on capacity + nothing blocks expansion. Rank the opportunity **and** name the binding constraint.

## Principles (non-negotiable)

1. **Python computes, the LLM narrates.** Every number comes from a tool result. The model never does arithmetic.
2. **Tag every claim:** `[data: source]`, `[domain: KB-id]`, `[assumption: A-xx]`.
3. **Source routing is deterministic** (code picks the source from the period, not the LLM).
4. **No silent gaps.** If data can't answer, say so and offer the nearest supported answer.
5. **Everything changeable lives in files:** weights/thresholds → `config.yaml`; facts → `kb/constraints.yaml`; judgment calls → `kb/assumptions.yaml`.

## Scoring

`score = 0.35·Growth + 0.35·Pressure + 0.30·Scale` (0–100)

- **Growth** = mean of percentiles: latest-12-months vs 2019, and CAGR 2022→latest. (T-100)
- **Capacity Pressure** = mean of percentiles: load factor, and seats-per-departure trend. (T-100)
- **Scale** = percentile of annual enplanements. (T-100) No log (percentile is rank-only).
- Percentiles are computed within the **national** FAA hub-class peer group, *then* filtered by region.
- Lenses: *absolute* (default weights), *pressure* (Scale 0, Growth 0.5, Pressure 0.5).
- What-if weights from chat: session-only, validated (non-negative, normalized to 1), printed in every answer.
- Congestion is **not** in the score; it feeds the constraint label.

**Binding constraint label** (first match wins; thresholds in config):

| Label | Rule |
|---|---|
| Regulatory | Hard cap/curfew in `constraints.yaml` **and** utilization ≥ 85% of cap |
| Airfield | Departures/runway ≥ p75 of peers, **or** NAS delay share ≥ p75 (if available), **or** A-09 signature |
| Terminal | Growth ≥ p60 **and** Pressure ≥ p60, and nothing above fired |
| None evident | Otherwise |

**Flags** (beside the score, never in it): low confidence (non-hub, seasonal, missing months); ULCC share high (if airport×carrier data exists); live disruption (active GDP / ground stop).

## Data

| Source | Use |
|---|---|
| BTS T-100 Segment Summary by origin (Socrata `data.bts.gov`, id `r495-tyji`, no key) | Monthly departures, passengers, seats, LF, distance, intl share |
| FAA NAS Status (`nasstatus.faa.gov`, no key) | Live delays, GDPs, ground stops, runway config, arrival rate |
| OpenSky (OAuth client credentials) | Departures with estimated destination, **≤7-day window**, recent only |
| OurAirports CSV | State, coordinates, runway count |
| TranStats route-level T-100, delay causes | ⚠️ Runtime fetchability unverified (Phase 0) |

- Live calls + local TTL cache in `.cache/`. Aggregate server-side with SoQL; never pull millions of rows.
- Known gaps (state them in answers): no gate counts or terminal sq ft ("demand is pressing", never "terminal is full"); no live route-level API; T-100 lags a few months; no fares.

**Period → source routing** (in `routing.py`): last 7 days → OpenSky; month/season/year → TranStats route-level if Phase 0 confirms, else T-100 summary as an explicitly stated approximation; specific past day / anything else → unsupported, offer nearest period.

## Knowledge base (`kb/`)

- `constraints.yaml` entry: `id, airport, type (cap|curfew|runway|schedule-level), statement, value, source_url, verified_on, confidence`.
- `assumptions.yaml` entry: `id, statement, value, why, alternatives_considered, sensitivity, owner, last_reviewed`.
- The agent cites entry IDs. Unverified entries must say so.

## The four questions

1. **New England terminal candidates:** `rank_airports(region="new_england")`, both lenses + constraint label. Must say: BOS wins on scale, pressure lens surfaces mid-size airports, no gate data.
2. **LAX vs SNA congestion:** `compare_airports`, `get_constraints`. Separate airfield / demand / regulatory. SNA is capped by law (agreement to 2030); LAX limit is soft.
3. **% long-haul out of ANC:** `route_mix("ANC", period, include_cargo)`. State definition (A-05, >4,000 km; 3,500 km sensitivity), window, source, passenger vs cargo split, upward bias from missing small Alaskan flights.
4. **SFO unmet demand:** `demand_signals`, `get_constraints`, `live_status`. Unmet demand isn't observable: show five traces + A-10 upper-bound estimate. Airfield-limited; lever is gauge.

## Agent design

Tools return `{values, formula, sources, assumptions, confidence}`:
`rank_airports(states|region, lens, weights=None)`, `compare_airports(codes, metrics=None)`, `route_mix(airport, period, threshold_km=None, include_cargo=False)`, `demand_signals(airport)`, `get_constraints(airport)`, `live_status(airport)`, `get_assumption(id)`.

- LLM: parse the question (airports, region, period, follow-ups), pick tools, narrate with tags, ask when ambiguous.
- LLM never: arithmetic, source selection, numbers absent from tool results.
- **Grounding check:** after each answer, code extracts every number and verifies it appears in that turn's tool results; unmatched numbers are flagged.
- Stack: Python, Claude API tool use, Streamlit chat with session memory.

Layout: `sources/` (bts, faa, opensky, ourairports, cache) · `metrics.py` · `scoring.py` · `routing.py` · `tools.py` · `agent.py` · `app.py` · `config.yaml` · `kb/` · `tests/`.

## Validation

- Unit tests for every metric with hand-computed fixtures.
- Golden tests for the four questions: call tools directly (no LLM), assert structure + sanity ranges.
- A-09 backtest: constrained (SFO, LGA, DCA, EWR, SNA) vs comparable unconstrained airports. If the signature doesn't separate them, drop it from the Airfield rule and report that.
- Grounding check on every agent answer.

## Repo rules

- Work **only inside this repo**. Never create another repo, directory or remote outside it.
- Data is never committed; it's cached in `.cache/` (gitignored). KB files are committed.
- Secrets in `.env` (gitignored); `.env.example` lists `ANTHROPIC_API_KEY`, `OPENSKY_CLIENT_ID`, `OPENSKY_CLIENT_SECRET`.
- Commit after every phase with a clear message. Don't start a phase until Nimrod says so.
- Nimrod must be able to defend every line: keep code simple and explicit.
