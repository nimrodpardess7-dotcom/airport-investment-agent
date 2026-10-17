# Airport Investment Agent: Design

An AI agent that helps an investor decide **where new U.S. passenger-terminal capacity would pay off, and what blocks it**. It answers in plain English, from live public aviation data, and shows how every number was produced.

## 1. Thesis

A terminal pays back per passenger. A good opportunity is **many passengers + growing demand + demand already pressing on capacity + nothing blocking expansion**.

More terminal doesn't always mean more flights. Some airports are limited by their terminal, some by their runways, some by law. So the agent ranks the opportunity **and** names the binding constraint, which is what makes a recommendation actionable.

## 2. Architecture

```
 question ─► Claude (agent.py) ─► tools.py ─► scoring.py ─► metrics.py ─► sources/ ─► live APIs
                │   picks tools,      │ formats     │ score,      │ pure math     │ fetch + TTL cache
                │   writes answer     │ results     │ label,                      (BTS T-100, TranStats,
                ▼                     ▼             │ flags                        FAA, OpenSky, OurAirports)
          grounding.py ◄──── every tool result ─────┘
          (every number in the answer must appear in a tool result)
                │
                ▼
          app.py (Streamlit chat + "How this answer was built" panel)
```

Everything changeable lives in three files, each readable and editable: `config.yaml` (weights and thresholds), `kb/constraints.yaml` (sourced facts) and `kb/assumptions.yaml` (judgment calls).

## 3. Scoring methodology (deterministic, no LLM)

**Opportunity Score (0–100)** = 0.35 × Growth + 0.35 × Pressure + 0.30 × Scale [A-01]

| Component | Metrics (each turned into a percentile) | Compared against |
|---|---|---|
| Growth | Latest 12 months vs 2019 (recovery); CAGR since 2022 (momentum) [A-04] | Same FAA hub class |
| Pressure | Load factor; up-gauging (seats per departure vs 2019) | Same FAA hub class |
| Scale | Passengers, latest 12 months | **All airports** |

- **Percentiles, not raw values.** One giant airport can't squash the rest, and metrics on different scales become comparable.
- **Peer groups.** Growth and pressure are ranked within FAA hub classes (large ≥ 1% of national boardings, medium ≥ 0.25%, small ≥ 0.05%, non-hub) [A-02], because +5% means something different at Boston and at Burlington. Scale is ranked nationally because size is absolute.
- **National first, region second.** Airports are ranked against the whole country, then filtered (e.g. to New England), since a region alone has too few airports to rank fairly.
- **Lenses and what-ifs.** The *pressure* lens sets the scale weight to 0, to surface mid-size airports running out of room. What-if weights from chat ("growth matters twice as much") are validated and normalized in code, and every answer prints the weights used.
- **Time windows.** "Latest 12 months" = the latest 12 published months, rolling. 2019 and 2022 are calendar years, so every comparison is a full year against a full year.

**Binding-constraint label.** Rules are checked in order; the first match wins. Congestion is kept out of the score on purpose: it decides *what to invest in*, not *how attractive* the airport is.

| Label | Rule | Meaning for the investor |
|---|---|---|
| Regulatory | Hard passenger cap on file and passengers ≥ 85% of it [A-12] | Money can't unlock growth; watch the legal timeline |
| Airfield | Runway/ATC (NAS) delay share ≥ p75 of peers [A-14], or a documented runway-geometry fact | A bigger terminal adds no flights; the lever is larger aircraft |
| Terminal | Growth and Pressure both ≥ p60 [A-13] | Best case for terminal investment |
| None evident | Otherwise | Demand isn't pressing on capacity yet |

**Flags** sit next to the score, never inside it: non-hub, borderline peer group, highly seasonal [A-18], missing months [A-19] and cargo-heavy [A-20]. Live FAA disruptions (ground delay programs, ground stops) are reported by the `live_status` and `demand_signals` tools, not folded into the score.

## 4. Where and how AI is used

**Claude (Opus 5.5) does three things:** understands the question (airports, region, period, follow-ups, what-ifs), picks which of 7 tools to call, and explains the results with source tags. **It never computes.**

| Guardrail | How |
|---|---|
| Python computes every number | Tools return display-ready strings ("92%", "36.59M"); the prompt says to quote them verbatim |
| Arguments are always valid | Strict JSON schemas; e.g. the lens can only be `absolute` or `pressure` |
| The LLM never picks the data source | `routing.py` maps the period to a source in code ("last 7 days" → OpenSky; a month or year → TranStats; a single day → unsupported, with the nearest option) |
| Numbers are checked after every answer | `grounding.py` flags any number not found in that session's tool results or the user's own words; the flag is shown under the answer |
| Ambiguity is surfaced, not guessed | "Portland" → asks PWM or PDX, with no tools called [A-17] |
| Every claim is traceable | Tags: `[data: source, window]`, `[domain: KB-id]`, `[assumption: A-id]` |

The system prompt is a file (`prompts/system.md`), the tool loop is about 30 lines (`agent.py`), and conversation history gives the chat its memory.

## 5. Key tradeoffs

| Decision | Chose | Over | Why / cost |
|---|---|---|---|
| Normalization | Percentiles | Min-max | Robust to outliers; loses "how much better" |
| Output | Score **+** separate label | One blended score | A blend hides *why* an airport scores high and *what* to invest in |
| Score data | T-100 summary (official API, instant) | TranStats detail (fresher by 3 months) | Stability for every question. Cost: freighters are mixed in, so cargo hubs get a flag |
| Passenger vs cargo | Airline-filed aircraft type (TranStats) | Guessing from callsigns | The guess missed ~50% of Anchorage freighters (Cathay, Korean, EVA use passenger callsigns) |
| Airfield trigger | Measured NAS delay share | Departures per runway | The runway count fired for 40% of airports; NAS share catches the known-constrained ones (SFO, LGA, EWR, DCA, BOS, JFK, ORD) |
| Lost capacity | Arrivals per hour (54 → 40 at SFO) | Daily or yearly totals | A daily figure would need a guess about operating hours |
| Facts | Small structured KB (9 sourced entries) | RAG over documents | Exact, testable lookups. RAG is right once the KB becomes unstructured documents |
| Data freshness | Live APIs + short cache | Static snapshot | Meets the brief. Cost: depends on external uptime and the T-100 publication lag |
| Agent loop | 30-line manual loop | SDK tool runner (beta) | Every step visible and defensible; no beta dependency |
| Weights | Judgment, made editable | "Optimal" weights | No ground truth exists, so weights are shown in every answer and recorded in the register |

## 6. Assumptions and uncertainty

- **20 assumptions** in `kb/assumptions.yaml`, each with the statement, why, alternatives considered and sensitivity. The agent cites them, and users can ask "why A-05?".
- **9 curated facts** in `kb/constraints.yaml`, each with a source URL, verification date and confidence (5 verified, 4 medium).
- **Stated in answers, never hidden:**
  - No public gate counts or terminal floor area: the agent says "demand is pressing", never "the terminal is full".
  - T-100 lags by months: the score uses May 2025–Apr 2026; delay data runs to Jul 2026.
  - T-100 counts boardings; total passengers ≈ boardings × 2 [A-07], within 1% of LAX's reported 2025 total.
  - NAS delay data covers reporting airlines only.
  - SNA's 2026 cap is 12.2M or 12.5M (tier unconfirmed); the label is Regulatory either way (92% / 89%).
  - Unmet demand is not observable; the agent shows five indirect traces.
  - Up-gauging also reflects fleet strategy, so the A-09 "up-gauging signature" is display-only, never a trigger.
- **Grounding limits.** Numbers are matched by value, so a coincidental match can pass. The check catches invented and rounded numbers, not wrong *claims* without numbers. Labels therefore come straight from tool output.

## 7. Validation

- **74 automated tests:** unit tests with hand-computed fixtures (metrics, scoring rules, grounding); golden tests for the four questions on live data, with no LLM; and offline agent-loop tests with a fake client.
- **End-to-end eval** (`tests/eval_questions.yaml`): the four questions + follow-up, what-if, ambiguous name and unanswerable question. Graded in code (right tools, required facts and caveats, clean grounding). **8/8 passed, $0.42** ([eval_results.md](eval_results.md)). It's one run of 8 cases, so it shows the system works, not a measured reliability rate.
- **Phase 0 findings** ([phase0_findings.md](phase0_findings.md)) record every data source's availability, latency and fallback, plus decisions D1–D5.

## 8. Cuts and future work

Cut for the one-day scope, each stated rather than hidden:
- **Voice** (bonus).
- **ULCC flag:** airport × carrier data works, but the threshold [A-11] isn't set.
- **A-09 backtest:** not run; the signature stays display-only.
- **Broad generalization testing** beyond the eval set.

Future work: RAG over airport master plans; gate and terminal-area data; fares (DB1B); FAA ASPM; scheduled demand vs arrival rate by hour; an admin UI for weights and the KB; deployment.
