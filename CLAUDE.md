# CLAUDE.md

Airport Investment Intelligence Agent. Full spec: `docs/PLAN.md` (single source of truth; this file condenses sections 2–8 and 12).

**Assignment requirements (the bar for "done"):**
- Deterministic scoring or ranking logic (not only LLM output).
- A chat interface to talk with the agent (voice is a bonus).
- Clearly communicate assumptions, uncertainty and scoping.
- Deliverables: source code + a **short** design/architecture doc covering scoring methodology, key tradeoffs, and where/how AI is used.
- Scoped for ~1 day: **clarity, reasoning and thoughtful design over completeness or polish.**

**Thesis:** a terminal pays back per passenger. Good opportunity = many passengers + growing demand + demand pressing on capacity + nothing blocks expansion. Rank the opportunity **and** name the binding constraint.

## Principles (non-negotiable)

1. **Python computes, the LLM narrates.** Every number comes from a tool result. The model never does arithmetic.
2. **Tag every claim:** `[data: source]`, `[domain: KB-id]`, `[assumption: A-xx]`.
3. **Source routing is deterministic** (code picks the source from the period, not the LLM).
4. **No silent gaps.** If data can't answer, say so and offer the nearest supported answer.
5. **Everything changeable lives in files:** weights/thresholds → `config.yaml`; facts → `kb/constraints.yaml`; judgment calls → `kb/assumptions.yaml`. **Every config threshold has an A-ID.**
6. **Every answer states its data window** (e.g. "T-100 through May 2026", "OpenSky, Oct 8–14").

## Scoring

`score = 0.35·Growth + 0.35·Pressure + 0.30·Scale` (0–100)

- **Growth** = mean of percentiles: latest-12-months vs 2019, and CAGR 2022→latest. (T-100)
- **Capacity Pressure** = mean of percentiles: load factor (latest 12 months), and up-gauging = % change in seats per departure, latest 12 months vs 2019. (T-100)
- **Scale** = percentile of enplanements over the latest 12 months. (T-100) No log (percentile is rank-only).
- **Time windows:** "latest 12 months" = latest 12 published months, rolling; 2019 and 2022 = calendar years. Always full year vs full year.
- Universe: >10,000 enplanements (A-03) first, then FAA hub class by share of national enplanements (A-02: 1% / 0.25% / 0.05%), with a "borderline class" note near cutoffs. T-100 segment passengers proxy enplanements (A-16).
- Percentiles are computed within the **national** peer group, *then* filtered by region.
- Lenses: *absolute* (default weights), *pressure* (Scale 0, Growth 0.5, Pressure 0.5).
- What-if weights from chat: session-only, validated (non-negative, normalized to 1), printed in every answer.
- Congestion is **not** in the score; it feeds the constraint label.

**Binding constraint label** (first match wins; thresholds in config):

| Label | Rule |
|---|---|
| Regulatory | Hard **passenger** cap in `constraints.yaml` **and** passengers (A-07) ≥ 85% of it (A-12). Other caps/curfews are facts only, never triggers |
| Airfield | Departures per *effective* runway ≥ p75 of peers (A-14), **or** NAS delay share ≥ p75 (reporting airlines only), **or** a runway-geometry entry in `constraints.yaml` |
| Terminal | Growth ≥ p60 **and** Pressure ≥ p60 (A-13), and nothing above fired |
| None evident | Otherwise |

A-09 "up-gauging signature" (up-gauging ≥ p75 **and** departures change vs 2019 ≤ p50) is **display-only**: shown as a trace, never a trigger.

Effective runway (A-15) = open **and** ≥ 5,000 ft. Close-parallel/crossing geometry lives in `constraints.yaml`, not code.

**Flags** (beside the score, never in it): low confidence (non-hub; seasonal = peak/trough month ≥ 2.0 (A-18); ≥1 missing month, component n/a if >3 missing (A-19)); cargo-heavy = freighters ≥ 25% of departures (A-20); ULCC share high (A-11, airport×carrier seats from TranStats); live disruption (active GDP / ground stop).

## Data

| Source | Use |
|---|---|
| BTS T-100 Segment Summary by origin (Socrata `data.bts.gov`, id `r495-tyji`, no key) | **Powers the score.** Monthly departures, passengers, seats, LF, distance, intl share. No carrier/aircraft type: freighters mixed in → cargo-heavy flag |
| TranStats T-100 Segment All Carriers (form download, no key) | Route × carrier × `AIRCRAFT_CONFIG`. Route mix for any month/season/year with an **exact passenger/cargo split**; ULCC share; cargo-heavy flag. ~6 MB / ~35 s per year, cached |
| TranStats delay causes (form download, no key) | NAS delay share for the Airfield rule. Reporting airlines only |
| FAA NAS Status (`nasstatus.faa.gov`, no key) | Live delays, GDPs, ground stops, runway config, arrival rate. Only airports with an active event are listed |
| OpenSky (OAuth client credentials) | "Last 7 days" only: departures with estimated destination. ~2 days per request → 7 days in chunks. **All flights, no passenger/cargo split.** ICAO codes (PANC) via OurAirports. Count and report null destinations. Non-commercial free tier |
| OurAirports CSV | State, coordinates, runways |

- Live calls + local TTL cache in `.cache/`. Aggregate Socrata server-side with SoQL; never pull millions of rows.
- Phase 0 results and decisions D1–D5: `docs/phase0_findings.md`.
- Known gaps (state them in answers): no gate counts or terminal sq ft ("demand is pressing", never "terminal is full"); no live route-level API; T-100 lags a few months; no fares.

**Period → source routing** (in `routing.py`): last 7 days → OpenSky (all flights); month/season/year → TranStats route-level; specific past day / anything else → unsupported, offer nearest period.

## Knowledge base (`kb/`)

- `constraints.yaml` entry: `id, airport, type (cap|curfew|runway|schedule-level), statement, value, source_url, verified_on, confidence`.
- `assumptions.yaml` entry: `id, statement, value, why, alternatives_considered, sensitivity, owner, last_reviewed`.
- The agent cites entry IDs. Unverified entries must say so.

## The four questions

1. **New England terminal candidates:** `rank_airports(region="new_england")`, both lenses + constraint label. Must say: BOS wins on scale, pressure lens surfaces mid-size airports, no gate data.
2. **LAX vs SNA congestion:** `compare_airports`, `get_constraints`. Separate airfield / demand / regulatory. SNA is capped by law at 12.2M (12.5M tier unconfirmed; Regulatory either way; agreement to 2030); LAX limit is soft.
3. **% long-haul out of ANC:** `route_mix("ANC", period, include_cargo)`. State definition (A-05, >4,000 km; 3,500 km sensitivity), window, source, passenger vs cargo split from TranStats `AIRCRAFT_CONFIG` (A-06; a 7-day OpenSky answer gives all flights only), upward bias from missing small Alaskan flights.
4. **SFO unmet demand:** `demand_signals`, `get_constraints`, `live_status`. Unmet demand isn't observable: show five traces + A-10 capacity loss per hour (KB 54 → 40, plus live FAA rate when listed; no daily extrapolation). Airfield-limited; lever is gauge.

## Agent design

Tools return `{values, formula, sources, assumptions, confidence}`:
`rank_airports(states|region, lens, weights=None)`, `compare_airports(codes, metrics=None)`, `route_mix(airport, period, threshold_km=None, include_cargo=False)`, `demand_signals(airport)`, `get_constraints(airport)`, `live_status(airport)`, `get_assumption(id)`.

- LLM: parse the question (airports, region, period, follow-ups), pick tools, narrate with tags, ask when ambiguous.
- LLM never: arithmetic, source selection, numbers absent from tool results.
- **Grounding check:** after each answer, code extracts every number and verifies it appears in that turn's tool results; unmatched numbers are flagged. Tools return a `display` string per value; the LLM quotes it verbatim and the check matches against it.
- Ambiguous names (Portland, Washington) → clarifying question, never a guess (A-17).
- Stack: Python, Claude API tool use, Streamlit chat with session memory.

Layout: `sources/` (bts, faa, opensky, ourairports, cache) · `metrics.py` · `scoring.py` · `routing.py` · `tools.py` · `agent.py` · `app.py` · `config.yaml` · `kb/` · `tests/`.

## Validation

- Unit tests for every metric with hand-computed fixtures.
- Golden tests for the four questions: call tools directly (no LLM), assert structure + sanity ranges.
- A-09 backtest: constrained (SFO, LGA, DCA, EWR, SNA) vs comparable unconstrained airports. Report whether the signature separates them; it stays display-only either way.
- Grounding check on every agent answer.
- Eval set (~12 questions) in `tests/eval_questions.yaml`, end-to-end: the four questions, a follow-up, a weight what-if, an ambiguous name, an unsupported period, an unknown code, an unanswerable question. Pass = right tools, clean grounding, required caveats.

## Repo rules

- Work **only inside this repo**. Never create another repo, directory or remote outside it.
- Data is never committed; it's cached in `.cache/` (gitignored). KB files are committed.
- Secrets in `.env` (gitignored); `.env.example` lists `ANTHROPIC_API_KEY`, `OPENSKY_CLIENT_ID`, `OPENSKY_CLIENT_SECRET`.
- Commit after every phase with a clear message. Don't start a phase until Nimrod says so.
- Build split: Claude Code writes `sources/`, `tools.py`, `agent.py`, `app.py`. Nimrod reviews `scoring.py` and the label rules line by line before they're committed.
- Nimrod must be able to defend every line: keep code simple and explicit. **Prefer the simple option; avoid complicated machinery.**
