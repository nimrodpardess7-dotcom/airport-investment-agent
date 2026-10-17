# Fix round report: answer quality (Q1, Q3, Q4)

Outputs: [q1.md](q1.md), [q3.md](q3.md), [q4.md](q4.md). All three answers passed the grounding check with no flagged numbers. Total cost $0.20; 92 tests pass.

## Root cause of the "missing" airports (Q1)
Not a scoring bug, and not A-03 or A-19. All 17 New England airports in the universe were evaluated, each with 12 of 12 months.
- `top=10` silently cut ACK (#14) and MHT (#15).
- The answer's table showed only 6 of the 10 rows it received, dropping BTV, PVD and MVY.
- A-03 also left out 39 smaller New England airports (no more than 10,000 boardings) without saying so.

**Fix:** every ranking now returns the number evaluated, the number shown, the airports below the top N, the airports without a score, and the airports below the universe, plus a one-line `summary`. The prompt requires that line in the answer.

## What changed
| Issue | Change |
|---|---|
| P0.1 exclusions | `summary`, `not_shown`, `score_not_available`, `below_universe` in every ranking |
| P0.2 magnitudes | Raw value next to every percentile (`raw`); SFO traces each carry a percentile |
| P0.3 label triggers | Structured `label_evidence` (rule, metric, value, percentile, bar, passed) and `near_misses` |
| P0.4 flags | Carrier concentration, ULCC share, low base; `flag_checks_not_run`; HVN expansion added as `project` fact HVN-01 (approved, upheld in court Jul 21, 2026; not under construction) |
| P0.5 SFO "how much" | Recovery-gap estimate (2.06M boardings, about 14,700 departures); A-10 upper bound (238 arrivals, about 33,300 passengers a day); timing note (rule effective 2026-03-31, about 1 month of the data window) |
| P1.6 route mix | Shares by departures, passengers and seats, all flights incl. cargo, top 5 long-haul destinations, summer/winter, combi counted as passenger |
| P1.7 time window | "latest" = the score's 12 months everywhere (2025-05 to 2026-04) |
| P1.8 register | A-06 matches the method, A-06a retired, A-10 and A-11 rewritten; test that every cited A-ID and KB-ID exists |
| P1.9 both lenses | Every ranking row carries its score and rank under the other lens |
| P2 prompt | Lead names the driver and the biggest risk; conditions in plain words; no absolute claims from proxies; competing explanation for "why"; unit stated; tags inline (max 3); one-line exclusions; one-sentence normalization; "(news report, unconfirmed)" |
| Framing (from the brief) | Labels now say what to invest in: Airfield = airfield projects, not a dead end. README and DESIGN reframed to "modernization, flight and passenger capacity" |

## New and changed assumption IDs
| ID | What |
|---|---|
| A-10 (rewritten) | Capacity-loss upper bound = lost arrivals/hour × 17 h (FAA designated hours) × seats per flight × load factor |
| A-11 (set) | ULCC flag: ≥ 25% of seats; carriers NK, F9, G4, SY, XP, MX |
| A-21 | Near miss: within 5 points of a bar |
| A-22 | Carrier concentration: one airline ≥ 50% of seats |
| A-23 | Low base: growth ≥ p90 with < 250,000 boardings in 2019 |
| A-24 | Recovery gap vs peer median (estimate) |
| A-25 | Combi aircraft count as passenger in route mix |
| A-26 | One window: "latest" = the score's 12 months |
| A-27 | Seasons: summer Jun–Aug, winter Dec–Feb |
| A-06a | Retired (callsign list) |

## Cut, and why
- **Winter across two calendar years:** within the 12-month window, winter = Dec 2025 + Jan–Feb 2026, which is complete. A calendar-year request (e.g. "2025") uses Jan, Feb and Dec of that year. Stated by A-27, not fixed further.
- **Carrier names:** flags show airline codes (XP = Avelo). Names would need a new download field; low value for the time left.
- **Re-tuning thresholds against distributions:** the new thresholds are set from one look at the distribution (e.g. ULCC ≥ 25% is about p90), not tuned.
