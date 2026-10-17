# Design

**Question:** where would new U.S. passenger-terminal capacity pay off, and what blocks it?

**Thesis:** a terminal pays back per passenger. A good opportunity = many passengers + growing demand + demand pressing on capacity + nothing blocking expansion. More terminal doesn't always mean more flights, so the agent ranks the opportunity **and** names the binding constraint.

```
question → Claude (agent.py) → tools.py → scoring.py → metrics.py → sources/ → live APIs
               ↓
       grounding.py: every number in the answer must appear in a tool result
```

## 1. Scoring (deterministic, no LLM)

**Score (0–100)** = 0.35 × Growth + 0.35 × Pressure + 0.30 × Scale

| Component | Metrics | Ranked against |
|---|---|---|
| Growth | Latest 12 months vs 2019; CAGR since 2022 | Same FAA hub class |
| Pressure | Load factor; seats per departure vs 2019 | Same FAA hub class |
| Scale | Passengers, latest 12 months | All airports |

- **Percentiles, not raw values:** one giant airport can't squash the rest.
- **Peer groups:** +5% growth means different things at Boston and at Burlington. Size is absolute, so Scale is ranked nationally.
- **National first, then filter by region:** New England alone is too small to rank fairly.
- **Lenses and what-ifs:** the *pressure* lens sets Scale to 0. Chat weights ("growth matters twice as much") are validated and normalized in code and printed in every answer.

**Label** (first match wins; kept out of the score because it decides *what* to build):

| Label | Rule | Meaning |
|---|---|---|
| Regulatory | Hard passenger cap, ≥ 85% used | Money can't unlock growth |
| Airfield | Runway/ATC delay share ≥ p75 of peers, or documented runway geometry | A terminal adds no flights; build for larger aircraft |
| Terminal | Growth and Pressure ≥ p60 | Best case for terminal capex |
| None evident | Otherwise | Demand isn't pressing yet |

**Flags** (beside the score, never in it): non-hub, borderline peer group, highly seasonal, missing months, cargo-heavy.

## 2. Where AI is used

Claude (Opus 5.5) understands the question, picks from 7 tools, and explains the results. **It never computes.**

- Tools return formatted numbers; the prompt says to quote them verbatim.
- Strict tool schemas keep arguments valid.
- Code, not the LLM, maps the time period to a data source.
- **Grounding check:** any number not found in a tool result is flagged under the answer.
- Ambiguous names ("Portland") → it asks instead of guessing.
- Every claim is tagged `[data]`, `[domain: KB-id]` or `[assumption: A-id]`.

## 3. Key tradeoffs

| Chose | Over | Why |
|---|---|---|
| Percentiles | Min-max | Robust to outliers; loses "how much better" |
| Score + separate label | One blended score | A blend hides *why* and *what to build* |
| T-100 summary API for the score | Detailed TranStats files | Instant and stable; freighters mixed in, so cargo hubs are flagged |
| Airline-filed aircraft type for cargo | Guessing from callsigns | Callsigns missed ~50% of Anchorage freighters |
| NAS delay share for Airfield | Departures per runway | The runway rule fired for 40% of airports; NAS share catches SFO, LGA, EWR, DCA, BOS, JFK, ORD |
| Small sourced KB | RAG over documents | Exact, testable lookups for ~10 facts |
| Weights shown and editable | "Optimal" weights | No ground truth exists |

## 4. Assumptions and uncertainty

- 20 assumptions in `kb/assumptions.yaml` (why, alternatives, sensitivity) and 9 sourced facts in `kb/constraints.yaml` (5 verified, 4 medium confidence). The agent cites both.
- **Stated in answers, never hidden:**
  - No gate or floor-area data: "demand is pressing", never "terminal is full".
  - T-100 lags months: every answer states its window.
  - Boardings × 2 ≈ total passengers (within 1% for LAX).
  - Unmet demand isn't observable, so the agent shows indirect traces.
- **Grounding check limit:** it matches numbers by value, so it catches invented or rounded numbers, not wrong claims without numbers.
- **Validation:** 74 tests (hand-computed fixtures, live golden tests, offline agent loop); end-to-end eval **8/8, $0.42**. That's one run, so it shows the system works, not a reliability rate.

## 5. Cuts

Voice; the low-cost-carrier flag (data ready, threshold unset); the up-gauging backtest (signal kept display-only); broad generalization testing. Future work: master-plan RAG, gate data, fares.
