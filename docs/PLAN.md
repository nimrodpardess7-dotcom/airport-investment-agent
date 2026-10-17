# Airport Investment Intelligence Agent: Plan v2

Deloitte Digital, Forward Deployed Engineer home assignment. Deadline: Sunday, Oct 18, 2026. Submission: public GitHub repo.
This file is the single source of truth. Copy sections 2–8 and 12 into the repo's `CLAUDE.md`.

---

## 1. Thesis

> **A terminal investment pays back per passenger. Good opportunity = many passengers + growing demand + demand already pressing on capacity + nothing blocks expansion.**

Every KPI must feed one of those four parts. If it doesn't, cut it.

**The key insight that shapes the design:** more terminal does not mean more flights. Some airports are limited by their terminal, some by their runways, and some by law. The agent ranks the opportunity **and** names the binding constraint. That is what makes the recommendation actionable.

---

## 2. Non-negotiable principles

1. **Python computes, the LLM narrates.** The model never calculates a number. Every number comes from a tool result.
2. **Every claim is tagged** with one of three labels:
   - `[data: source]`: a number from an API.
   - `[domain: KB-id]`: context from the knowledge base.
   - `[assumption: A-xx]`: a choice we made.
3. **Source routing is deterministic.** Code picks the data source from the question's time period. The LLM does not choose.
4. **No silent gaps.** If the data can't answer the question, the agent says so and offers the nearest answer it can support.
5. **Everything changeable lives in files.** Weights and thresholds go in `config.yaml`. Facts go in `kb/constraints.yaml`. Judgment calls go in `kb/assumptions.yaml`. Users and admins can read, challenge, and edit all three. **Every threshold in `config.yaml` has an A-ID** in the register.
6. **Every answer states its data window**, for example "T-100 through May 2026" or "OpenSky, Oct 8–14". An investor must always know how old the number is.

---

## 3. Scoring

### Opportunity Score (0–100)
```
score = 0.35 × Growth + 0.35 × Capacity Pressure + 0.30 × Scale
```

| Component | Built from | Source |
|---|---|---|
| Growth | Average of two percentiles: latest 12 months vs 2019 (recovery), and CAGR from 2022 to latest (momentum) | T-100 |
| Capacity Pressure | Average of two percentiles: load factor (latest 12 months), and up-gauging = % change in seats per departure, latest 12 months vs 2019 | T-100 |
| Scale | Percentile of enplanements over the latest 12 months, **ranked against all airports** (size is absolute) | T-100 |

**Time windows (one rule everywhere):** "Latest 12 months" means the latest 12 published months, rolling. 2019 and 2022 mean calendar years. Every comparison is full year vs full year, so seasonality cancels out.

- **Normalization:** growth and pressure metrics become percentiles within their **national** peer group (FAA hub class: large, medium, small, non-hub); Scale is ranked against all airports, because size is absolute. Only after that do we filter by region.
  - Why: New England alone has too few airports to rank against each other.
  - Why percentile and not min-max: one giant airport (ATL) does not squash everyone else.
- **No log of scale.** A percentile depends only on rank order, and log never changes rank order, so the log would be redundant.
- **Two lenses:**
  - *Absolute*: the default weights.
  - *Pressure*: Scale weight = 0, Growth and Pressure 0.5 each. This surfaces mid-size airports that are running out of room.
- **What-if weights from chat.** The weights apply to that session only. Code validates them (non-negative, normalized to 1). Every answer prints the weights it used.
- **Congestion is not in the score.** It feeds the constraint label below.

### Binding Constraint label (rules in code, thresholds in config)

Rules are checked in this order. The first one that matches wins.

| Label | Rule | Meaning for the investor |
|---|---|---|
| **Regulatory** | A hard **passenger** cap exists in `constraints.yaml` **and** passengers (A-07) ≥ 85% of it. Other caps (daily departures, loading bridges, curfew) are shown as facts and do not trigger the label. | Money can't unlock it. Watch the legal or political timeline. |
| **Airfield** | NAS (runway/ATC) delay share ≥ p75 of peer group (A-14; reporting airlines only), **or** a runway-geometry entry exists in `constraints.yaml`. Departures per effective runway and the A-09 up-gauging signature are shown as evidence but never trigger the label (Phase 1: the OR rule fired for 40% of airports). | A terminal adds no flights. The lever is gauge: widebody gates and bigger holdrooms. |
| **Terminal** | Growth ≥ p60 **and** Pressure ≥ p60 (A-13), and neither rule above fires | Best case for terminal capex. |
| **None evident** | Otherwise | Demand isn't pressing on capacity yet. |

**Effective runways (A-15).** A raw runway count is misleading.
- SNA has 2 runways, but one is a 2,887 ft runway used only by general aviation.
- SFO has 4 runways, but they form two pairs only 750 ft apart, so they behave like far fewer.

So we count only runways long enough for air carriers (length threshold in config). Close-parallel geometry isn't in any dataset, so it goes in `constraints.yaml` as a fact, and it feeds the Airfield rule directly.

### Flags (shown next to the score, never inside it)
- **Low confidence:** non-hub airports, highly seasonal airports, or missing months of data.
- **ULCC share high:** ultra-low-cost carriers run high load factors by design, which inflates the pressure signal. Airport × carrier seats come from TranStats (✅ Phase 0).
- **Cargo-heavy (A-20):** freighters ≥ 25% of departures. The score's T-100 summary mixes freighters into departures and seats per departure, so cargo hubs (ANC) are flagged rather than hidden.
- **Live disruption:** an active FAA Ground Delay Program or ground stop right now.

---

## 4. Data sources

| Source | Access | Status | Used for |
|---|---|---|---|
| BTS T-100 Segment Summary by Origin Airport | Socrata REST, `data.bts.gov` id `r495-tyji`, no key | ✅ Verified live (through Apr 2026 at Phase 0) | **Powers the score (D1).** Departures, passengers, seats, load factor, seats per flight, domestic vs outbound international, average distance. Monthly. No carrier or aircraft type: freighters are mixed in. |
| FAA NAS Status | REST, `nasstatus.faa.gov`, no key | ✅ Exists | Live delays, GDPs, ground stops, active runway configuration, arrival rate. The feed lists only airports with active events, so "not listed" means "no active event", not "error". |
| OpenSky Network | REST, free account (OAuth client credentials) | ✅ Verified | "Last 7 days" only. Departures by airport with estimated destination. **~2 days per request**, so 7 days = 4 chunked calls. No aircraft type, so it reports **all flights, no passenger/cargo split** (D2). Not for historical queries. Uses ICAO codes (PANC, not ANC), so we map them via OurAirports. The estimated destination is sometimes null; count those and report them, don't drop them silently. Free tier is non-commercial; note that in the README. |
| OurAirports | CSV over HTTP | ✅ Open | State, coordinates, runway count. Used for region filtering, distances, departures per runway. |
| TranStats T-100 route-level (origin × destination × carrier × aircraft config) | Form download by code, no key | ✅ Verified (through Jul 2026; 6 MB / ~35 s per year) | Route mix for any month, season or year (Q3), with an **exact passenger/cargo split** from `AIRCRAFT_CONFIG`; ULCC share; cargo-heavy flag (D1, D2) |
| TranStats delay causes (carrier × airport × month) | Form download by code, no key | ✅ Verified (12 months: 0.9 MB / ~5 s) | NAS delay share for the Airfield rule. Reporting airlines only (D3). |
| `kb/constraints.yaml` | Curated by hand, every entry sourced | Build | Legal caps, curfews, runway geometry, FAA schedule levels |

**Runtime model:** live API calls with a local TTL cache. The cache exists for speed, not as a substitute for the APIs. Aggregation happens server-side with SoQL (sums grouped by year), so we never pull millions of rows.

**Known gaps. State them in the doc and in answers.**
- No public gate counts or terminal square footage. The agent can say "demand is pressing", never "the terminal is full".
- No live route-level API.
- T-100 is published with a lag of a few months. "Latest" means the latest 12 published months.
- No public fares data in scope.

### Period → source routing (Q3 and any route-mix question)

| User asks about | Source |
|---|---|
| Last 7 days | OpenSky |
| A month, a season, or a year | TranStats route-level (✅ Phase 0), passenger/cargo split exact |
| A specific past day, or anything not covered | Say it isn't supported, and offer the nearest supported period |

---

## 5. Knowledge base (`kb/`)

Two files, both human-editable and both versioned in git. The agent cites entry IDs in its answers.

**`constraints.yaml`: facts about airports.**
Each entry has: `id`, `airport`, `type` (cap / curfew / runway / schedule-level), `statement`, `value`, `source_url`, `verified_on`, `confidence`.

**`assumptions.yaml`: judgment calls.**
Each entry has: `id`, `statement`, `value`, `why`, `alternatives_considered`, `sensitivity` (what changes if it's wrong), `owner`, `last_reviewed`.

### Initial assumptions register

| ID | Assumption | Why |
|---|---|---|
| A-01 | Weights 0.35 / 0.35 / 0.30 | Growth and pressure are the thesis. Scale matters because payback is per passenger, but size alone isn't opportunity. |
| A-02 | Peer groups = FAA hub class, computed from each airport's share of national enplanements: large ≥ 1%, medium ≥ 0.25%, small ≥ 0.05%, non-hub < 0.05% (49 U.S.C. 47102, ✅ verified). Applied **after** A-03. | Comparing BOS to Burlington is meaningless. Computed from T-100 (A-16), so an airport near a cutoff may land one class off from the FAA's official list. Such airports get a "borderline class" note. |
| A-03 | Universe = FAA primary airports (>10,000 enplanements per year). Applied **first**. | Below that, data is noise. This is the same line as the FAA's non-hub floor, so the two rules don't conflict. |
| A-04 | Growth = latest 12 months vs 2019, plus CAGR from 2022 | A plain 3–5 year CAGR is distorted by COVID |
| A-05 | Long-haul = over 4,000 km great-circle distance (Eurocontrol) | No single industry standard exists; this one is citable. The EU's 3,500 km is shown as a sensitivity check. |
| A-06 | Route mix counts passenger aircraft only by default; cargo is shown separately. The split comes from TranStats `AIRCRAFT_CONFIG`. OpenSky (last 7 days) reports all flights, no split. | The client invests in passenger terminals. ANC cargo would distort the answer. Callsign guessing was tested and dropped (D2): it missed about half of ANC freighters. |
| A-07 | Total passengers ≈ enplanements × 2 | Legal caps count everyone passing through; T-100 counts only boarding passengers |
| A-08 | "LA" = LAX; "Santa Ana" = SNA (John Wayne) | SNA's code belongs to Santa Ana. The agent offers to add BUR, LGB and ONT. |
| A-09 | **Hypothesis:** up-gauging ≥ p75 of peers **and** departures change vs 2019 ≤ p50 of peers signals an airfield constraint. **Display-only**, never a label trigger. | Airlines up-gauge when they can't add flights, but fleet strategy and pilot shortages also drive up-gauging, so it's shown as a trace and backtested (section 8), not used as proof. |
| A-10 | Lost arrival capacity = reference arrival rate − current arrival rate, **per hour**, from `constraints.yaml`; the live FAA rate is added when FAA lists the airport. | Investors want a number. Per hour needs no operating-hours guess (D4). |
| A-11 | ULCC flag threshold = __% of seats | Set in Phase 1 |
| A-12 | Utilization trigger for the Regulatory label = 85% of the cap | Judgment |
| A-13 | Terminal label needs Growth and Pressure ≥ p60 | Judgment. Recheck against the real distribution in Phase 1. |
| A-14 | Airfield label triggers at NAS delay share ≥ p75 of peers (or a geometry fact) | Measured evidence; catches SFO, LGA, EWR, DCA, BOS, JFK, ORD. Departures per runway is display-only. |
| A-15 | Effective runway = open (not marked closed in OurAirports) **and** at least the minimum length in config (start: 5,000 ft). One OurAirports row = one runway. | Excludes closed and general-aviation-only strips. SNA's 5,700 ft runway must still count. The count stays crude on purpose: crossing or close-parallel geometry (SFO) is handled by a `constraints.yaml` entry, which fires the Airfield label directly. |
| A-16 | T-100 segment passengers at origin are a proxy for enplanements | Segment data also counts through-passengers who stay on board, so it slightly overstates enplanements. It's the same bias for every airport, so the ranking holds. |
| A-17 | "Portland", "Washington" and other ambiguous names trigger a clarifying question, never a guess | PWM vs PDX; DCA vs IAD vs BWI |
| A-18 | Highly seasonal = busiest month ÷ quietest month ≥ 2.0, over the latest 12 months | Simple to explain. Recheck in Phase 1 against known seasonal airports (ACK, MVY) vs year-round ones. |
| A-19 | Data completeness: if any required 12-month window is missing 1 or more months, flag low confidence. If it's missing more than 3 months, don't compute that component; show it as n/a. | A partial year biases both growth and load factor |
| A-20 | Cargo-heavy flag = freighter departures ≥ 25% of all departures, latest full year (TranStats) | The score's summary data mixes in freighters; flag it, don't hide it (D1). Recheck the cut in Phase 1. |

### Initial constraints (verified in Phase 0; sourced entries in `kb/constraints.yaml`)

- **SNA**
  - Passenger cap 2026–2030: **12.2M**, or 12.5M if traffic and mitigation conditions were met. Which tier applies isn't publicly confirmed; the agent uses 12.2M and mentions 12.5M (D5). SNA is Regulatory either way (≈92% / 89%).
  - 95 Class A average daily departures through 2030. Loading bridges: no limit through 2030.
  - Curfew: departures allowed only 07:00–22:00 on weekdays, from 08:00 on Sundays; commitment runs through 2035.
  - One air-carrier runway, 5,700 ft. Narrowbody aircraft only.
- **LAX**
  - 78.9M was the Master Plan's demand forecast, not a cap. No hard passenger cap; about 73.7M passengers in 2025. **Soft limit.**
- **SFO**
  - Parallel runways are 750 ft apart.
  - Since Mar 31, 2026 the FAA bans side-by-side landings. Clear-weather arrivals fell 54 → 36 per hour, then rose to 40 on Aug 12, 2026 (42 planned). The live FAA rate appears only when SFO has an active event.
  - IATA Level 2 (schedule-facilitated): still to source.

---

## 6. The four questions

| # | Question | Tools | Approach | Must say |
|---|---|---|---|---|
| 1 | New England terminal candidates | `rank_airports(region="new_england", lens=…)` | National percentiles, then filter to CT, ME, MA, NH, RI, VT. Show both lenses and the constraint label for each airport. | BOS wins on scale. The pressure lens surfaces mid-size airports. No gate data exists. |
| 2 | LAX vs SNA congestion | `compare_airports(["LAX","SNA"])`, `get_constraints` | Separate three kinds of congestion: airfield, demand, regulatory | SNA is capped by law; money can't unlock it. Its agreement expires in 2030, which is a watch item. LAX has a soft limit. |
| 3 | % long-haul flights out of ANC | `route_mix("ANC", period, include_cargo)` | Route by period (section 4). Show distance buckets, the passenger vs cargo split (TranStats), and EU threshold sensitivity. A "last 7 days" answer gives all flights only. | State the definition, the time window, and the data source. Missing small Alaskan flights would bias the share upward. |
| 4 | SFO unmet demand and why | `demand_signals("SFO")`, `get_constraints`, `live_status` | Unmet demand is not observable. Present five traces: load factor, up-gauging vs departures, passengers vs flights recovery since 2019, Level 2 status, live delay programs. Add the A-10 per-hour capacity loss. | Airfield-limited: a terminal adds no landings. The lever is gauge (widebody gates). |

---

## 7. Agent design

**Tools.** Each returns `{values, formula, sources, assumptions, confidence}`.
- `rank_airports(states|region, lens, weights=None)`
- `compare_airports(codes, metrics=None)`
- `route_mix(airport, period, threshold_km=None, include_cargo=False)`
- `demand_signals(airport)`
- `get_constraints(airport)`
- `live_status(airport)`
- `get_assumption(id)`: lets users ask "why did you assume that?"

**What the LLM does:**
- Understands the question: airports, region, time period, follow-up references ("and Hartford?").
- Picks the tools.
- Narrates the result with tags.
- Asks a clarifying question when the request is ambiguous.

**What the LLM never does:**
- Arithmetic.
- Pick the data source.
- Produce a number that isn't in a tool result.

**Grounding guardrail (cheap, high value):** after each answer, code extracts every number from the response and checks it appears in that turn's tool results. Any unmatched number gets flagged.
- To avoid false alarms from rounding ("12.2M" vs 12,214,331), each tool returns a `display` string per value. The LLM must quote those strings verbatim. The check matches against them.

**Stack:** Python, Claude API tool use, Streamlit chat with session memory. Voice is a bonus, only if time is left.

**Code structure**
```
sources/      bts.py (Socrata + TranStats), faa.py, opensky.py, ourairports.py, cache.py
metrics.py    load_factor, growth, upgauging, departures_per_runway, route_buckets, …
scoring.py    percentile, score_airport, rank_airports, constraint_label
routing.py    period → source
tools.py      agent-facing wrappers (numbers + formula + sources + assumptions)
agent.py      tool-calling loop, system prompt, grounding check
app.py        Streamlit chat
config.yaml   weights, thresholds, regions, source settings
kb/           constraints.yaml, assumptions.yaml
tests/
```

---

## 8. Validation

- **Unit tests** for every metric, using hand-computed fixtures.
- **Golden tests** for the four questions: run the tools directly with no LLM, and assert on structure and sanity ranges.
- **Hypothesis A-09 backtest:**
  - Known constrained airports: SFO, LGA, DCA, EWR, SNA. Do they show the signature?
  - Comparable unconstrained airports: do they *not* show it?
  - If the signature doesn't separate the two groups, drop it from the Airfield rule and say so in the doc. A negative result reported honestly is a strong result.
- **Grounding check** on every agent answer (section 7).
- **Eval set** of about 12 questions in `tests/eval_questions.yaml`, run end-to-end:
  - The four assignment questions.
  - A follow-up ("and Hartford?").
  - A weight what-if ("growth matters twice as much").
  - An ambiguous name ("Portland").
  - An unsupported period ("long-haul share on March 3, 2024").
  - An unknown airport code.
  - A question the data can't answer ("how many gates does PVD have?").
  - Each one passes if the right tools are called, the grounding check is clean, and the required caveats appear.

---

## 9. Phases

| Phase | Work | Budget | Done when |
|---|---|---|---|
| 0. Verify ✅ | See the checklist below and `docs/phase0_findings.md` | 2h | Every ⚠️ in this doc is resolved or replaced by a stated fallback |
| 1. Core | Sources, metrics, scoring, label, KB files, tests. **No LLM.** | 5h | All four questions answerable by calling Python directly |
| 2. Agent | Tools, system prompt, routing, grounding check | 3h | The four questions work in plain English |
| 3. Chat | Streamlit with session memory | 1.5h | Follow-ups and weight what-ifs work |
| 4. Generalize | Any airport, region or period; edge cases | 2h | New questions work without code changes |
| 5. Docs | Design doc + README | 1.5h | Submittable |
| Bonus | Voice | Only if time is left | |

**Cut line if time runs short.** The things that must ship:
- The score and the label.
- The four questions working.
- Chat with follow-ups.
- The KB files.
- The design doc.

The first things to cut, in order:
1. Voice.
2. The ULCC flag.
3. NAS delay share.
4. Period routing beyond "last 7 days" and "full year".

Each cut is stated in the doc as a cut, not hidden.

**Phase 0 checklist** (✅ done; decisions D1–D5 recorded in `docs/phase0_findings.md`)
1. Can TranStats route-level T-100 be fetched by code at runtime? Measure size and download time.
2. Same check for the delay-causes file.
3. Check T-100 publication lag. Confirm what "latest 12 months" means in practice.
4. Create an OpenSky account. Run a test query for ANC departures over the last 7 days.
5. FAA NAS Status: test SFO and check which fields come back (arrival rate, GDP).
6. Is airport × carrier data available? If not, drop the ULCC flag.
7. Verify: SNA 2026–2030 cap; LAX 78.9M status; SFO current arrival rate. (Hub-class thresholds: ✅ done. PFC cap: dropped, because nothing computes with it.)

**Phase 0 ownership**
- **Nimrod:** create the OpenSky account, put all keys in `.env`, read the findings, and decide each fallback.
- **Claude Code:** write one small test script per source in `scripts/phase0/`, run them, and write `docs/phase0_findings.md`. For each source, the findings say: works or doesn't, fields returned, latency, size, and the recommended fallback.

---

## 10. Key tradeoffs (seed for the design doc)

- **Percentile vs min-max.** Chose percentile: robust to outliers. Cost: loses magnitude ("how much better").
- **One score + constraint label vs one blended score.** Chose separation: a blended score hides *why* an airport scores high and what to invest in.
- **Live APIs + cache vs a static snapshot.** Chose live, per the brief. Cost: dependency on external uptime and the T-100 lag.
- **Structured KB vs RAG.** Chose a structured KB: it holds about 20 facts, and lookups are exact and testable. RAG becomes right when the KB grows to unstructured documents (master plans, EIRs). That's listed as future work.
- **OpenSky 7-day sample vs annual data.** Annual is used when available; otherwise the sample is shown with its limits stated.
- **Weights are judgment, not science.** That's why they're editable, shown in every answer, and recorded in the assumptions register.

---

## 11. Out of scope / future work

- RAG over airport master plans and environmental documents.
- Admin UI for weights and the KB.
- Gate and terminal-area data.
- Fares data (DB1B).
- FAA ASPM (requires registration).
- Scheduled demand vs arrival rate by hour.
- Deployment.

---

## 12. Repository rules

- **One public GitHub repo** holds everything: code, `config.yaml`, `kb/`, tests, the design doc, the README, and `CLAUDE.md`. No second repo, and no files living only on the laptop or in a chat.
- Name: `airport-investment-agent`.
- Data is **not** committed. It's fetched live and cached in `.cache/`, which is gitignored. The KB files *are* committed.
- Secrets go in `.env` (gitignored). The repo ships a `.env.example` listing `ANTHROPIC_API_KEY`, `OPENSKY_CLIENT_ID`, and `OPENSKY_CLIENT_SECRET`.
- Manual setup (done by Nimrod, ~2 minutes):
  1. Create an empty public repo on GitHub.
  2. Clone it.
  3. Open Claude Code inside it.
- Claude Code then does everything else inside that folder. It must never create a repo or directory outside it.
- Commit after every phase with a clear message. The git history shows the step-by-step build.

---

## 13. Open decisions

- [x] Build split:
  - Claude Code writes `sources/`, `tools.py`, `agent.py` and `app.py`.
  - Nimrod reviews `scoring.py` and the constraint-label rules line by line before they're committed. Those are the parts the interview will probe.
- [ ] Set A-11 (ULCC threshold) and confirm the A-12 and Terminal-rule thresholds after seeing the real distributions in Phase 1.
