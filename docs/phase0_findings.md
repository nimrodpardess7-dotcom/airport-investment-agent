# Phase 0 findings

Run on 2026-10-15/16. Each source has a probe script in `scripts/phase0/`; raw results are saved to `.cache/phase0/*.json` (gitignored).
Re-run any script with `.venv/Scripts/python scripts/phase0/<name>.py` (from `scripts/phase0/`).

**Bottom line:** every ⚠️ in PLAN.md is resolved; two constraint facts carry a stated fallback. Both TranStats bulk sources **can be fetched by code at runtime**, which is better than PLAN assumed. Five decisions for Nimrod are listed at the end.

## Summary

| # | Check | Result | Recommended fallback / action |
|---|---|---|---|
| 1 | TranStats T-100 route-level at runtime | ✅ Works. One year: 6.3 MB zip, 571k rows, ~31–36 s. One month: 0.56 MB, ~7 s. Data through **Jul 2026**. | Use it for route mix (Q3) and ULCC. Cache one file per year. |
| 2 | TranStats delay causes at runtime | ✅ Works. 12 months: 0.9 MB zip, 22k rows, ~5 s. Through **Jul 2026**, 369 airports. | Keep NAS delay share in the Airfield rule (not cut). |
| 3 | T-100 publication lag | Socrata `r495-tyji`: latest **Apr 2026** (~6-month lag). TranStats: latest **Jul 2026** (~3-month lag). No missing months 2014–2025. | Decided in D1. Today "latest 12 months" on Socrata = May 2025 – Apr 2026. |
| 4 | OpenSky ANC, last 7 days | ✅ Works (OAuth). 2,129 PANC departures Oct 8–14, 2026. **~2-day limit per request** → 4 calls, ~0.5–1 s each, 30 credits each (4,000/day). 16.3% have no destination. | Use only for "last 7 days". Correct PLAN's "max 7-day window" to "7 days fetched as 2-day chunks". |
| 5 | FAA NAS Status | ✅ Works, no key, ~0.2 s. Arrival rate + runway config exist, **but only for airports currently listed** (SFO wasn't listed at test time). | A-10 uses KB rates (SFO-02) as the reference; the live rate is shown only when present. |
| 6 | Airport × carrier data | ✅ Available via TranStats route-level (not via Socrata). | Keep the ULCC flag; set A-11 in Phase 1. |
| 7 | SNA cap / LAX 78.9M / SFO rate | Resolved with caveats; see below. `kb/constraints.yaml` updated with sources. | SNA tier unconfirmed, but the label is the same either way. |

---

## 1. BTS T-100 Segment Summary by Origin Airport (Socrata `r495-tyji`) — `bts_t100.py`

- **Works.** No key. SoQL server-side aggregation is fast: all 1,311 origin airports for one year in **1.0 s / 92 KB**; single queries ~0.25 s.
- **Fields:** monthly totals per origin airport: departures, passengers, seats, load factor, seats/flight, distance/flight, payload, freight, mail, each split into domestic / outbound international / inbound international. `year` is text; `reporting_month` is a date.
- **Coverage:** Jan 2014 – Apr 2026. 2014–2025 have all 12 months; 2026 has 4.
- **No carrier column**, and **no aircraft-config column**:
  - `total_departures` includes all-cargo flights (zero seats). Seats per departure is diluted at cargo hubs: ANC shows **43.4 seats/departure** (latest 12 months) vs 129–170 at BOS/LAX/SFO. Departures per runway is inflated the same way.
  - So Socrata alone can't do the ULCC flag or a passenger-only departures count.
- **1,311 origin airports** includes foreign origins and tiny strips. Phase 1 filters to U.S. airports via OurAirports and applies A-03.
- Sanity read (latest 12 months May 2025 – Apr 2026 vs 2019, segment passengers = enplanement proxy, A-16):

| Airport | Pax latest 12m | Pax 2019 | LF | Seats/dep 2019 → now | Departures 2019 → now |
|---|---|---|---|---|---|
| LAX | 36.6M | 43.4M | 0.821 | 155.3 → 164.6 | 329,493 → 270,853 |
| SFO | 26.6M | 27.9M | 0.826 | 159.5 → 169.6 | 213,016 → 190,280 |
| BOS | 21.0M | 20.7M | 0.817 | 128.0 → 135.3 | 197,886 → 189,745 |
| SNA | 5.59M | 5.22M | 0.804 | 128.8 → 134.7 | 47,965 → 51,609 |
| PWM | 1.28M | 1.09M | 0.828 | 79.5 → 104.0 | 15,960 → 14,841 |

  SFO and LAX show the A-09 shape (more seats per flight, fewer flights). So do BDL, PWM and BTV, which the backtest must explain.

## 2. TranStats T-100 Segment, All Carriers (table FMG) — `transtats_t100_route.py`

- **Works at runtime.** The download page is an ASP.NET form; replaying its postback with the hidden fields returns a zip. Latest available: **July 2026**.
- **Size / latency:** 13 selected fields. One month (Jan 2025): 0.56 MB zip, 45k rows, 6.9 s. Full year 2025: **6.3 MB zip, 33.9 MB CSV, 571k rows, 31–36 s**.
- **Fields used:** `YEAR, MONTH, UNIQUE_CARRIER, ORIGIN, DEST, DEST_COUNTRY, DISTANCE (miles), DEPARTURES_PERFORMED, SEATS, PASSENGERS, FREIGHT, AIRCRAFT_CONFIG, CLASS`.
- **`AIRCRAFT_CONFIG` separates freighters exactly** (1 = passenger, 2 = freight, 3 = combi, 4 = seaplane). This is much better than callsign prefixes for any month/season/year query.
- **Q3 preview (ANC, calendar 2025, departures-weighted):**

| Aircraft | > 4,000 km (A-05) | > 3,500 km (EU) |
|---|---|---|
| Passenger aircraft only | 11.4% | 14.4% |
| All aircraft | 43.2% | 46.5% |
| Freighters only | 68.4% | — |

  ANC 2025 departures: 38,225 passenger, 48,963 freighter, 800 combi.
- **A-06a gap measured:** callsign prefixes from the config list would miss **50.3%** of ANC freighter departures (24,637 of 48,963). Carriers that fly *only freighters* through ANC still use their airline callsign: Cathay (CX), China Airlines (CI), Korean (KE), EVA (BR), Air China (CA), Asiana (OZ), plus Alaska Central Express (KO) and Alaska Airlines' own freighters (AS: 2,174). The IATA → ICAO mapping in this check is hand-made, so treat 50% as approximate.
- **ULCC seat share (2025, passenger aircraft; NK, F9, G4, SY as an illustrative set):** BOS 4.7%, BDL 6.0%, PVD 1.5%, PWM 2.5%, MHT 0.2%, LAX 6.0%, SNA 8.5%, SFO 2.7%. Reference: LAS 19.9%, MCO 22.6%, FLL 34.9%. Enough spread to set A-11 in Phase 1.

## 3. TranStats delay causes — `transtats_delay_causes.py`

- **Works at runtime.** `OT_DelayCause1.asp` is a plain form (`PeriodFrom` / `PeriodTo`, coded `year × 12 + month`). The resulting "Download Raw Data" link is a plain GET that returns `Airline_Delay_Cause.csv` in a zip.
- **Size / latency:** 12 months (Aug 2025 – Jul 2026): **0.9 MB zip, 22,345 rows, ~5 s**. 369 airports.
- **Fields:** year, month, carrier, airport, arr_flights, arr_del15, counts and minutes by cause (carrier, weather, NAS, security, late aircraft), cancelled, diverted.
- **Caveat:** it covers only the carriers that report on-time data (the large U.S. airlines), not every operator.
- **NAS share of delay minutes, Aug 2025 – Jul 2026:** SFO **46.5%**, EWR 41.4%, LGA 35.4%, BOS 34.4%, DCA 27.4%, SNA 17.3%, ANC 17.1%, LAX 15.5%, PVD 12.9%. The constrained airports rank high, so this signal looks useful for the Airfield rule.

## 4. OpenSky Network — `opensky.py`

- **Works with an account.** Anonymous calls return **403 "You cannot access historical flights"**. Auth is OAuth2 client credentials; tokens last 30 min.
- **Request limit:** the API docs limit flight queries to **~2 days per request** (PLAN said 7). A 7-day window = 4 chunked calls, 0.5–1 s and 30 credits each; a standard account has 4,000 credits/day per endpoint. Flights are batch-processed overnight, so the window ends at yesterday 00:00 UTC.
- **Fields:** `icao24, callsign, firstSeen, lastSeen, estDepartureAirport, estArrivalAirport` + distance/candidate-count quality fields. **No aircraft type or operator field**: cargo can only be guessed from the callsign.
- **ANC, Oct 8–14, 2026:** 2,129 departures, **348 (16.3%) with no estimated destination**. These are counted and reported, not dropped. Destinations are mapped to coordinates via OurAirports (ICAO).
- **Cross-check with T-100 (section 2):**

| Long-haul share (> 4,000 km) | OpenSky 7 days | T-100 2025 |
|---|---|---|
| All flights | 43.0% | 43.2% |
| "Passenger" | 25.2% (callsign rule) | 11.4% (`AIRCRAFT_CONFIG` = passenger) |

  The totals agree, which validates both sources. The passenger split doesn't: the callsign rule leaves freighters from Cathay (CPA), China Airlines (CAL), Korean (KAL), EVA, Alaska Central Express (AER), China Southern (CSG) and others in the "passenger" bucket. OpenSky also includes private/GA flights (N-registrations), which T-100 doesn't.
- **Conclusion:** OpenSky is fine for "what flew out of ANC this week". It isn't reliable for a passenger-only share. See D2 below.

## 5. FAA NAS Status — `faa_nas.py`

- **Works.** No key.
  - `/api/airport-events` (JSON): 0.2 s, 12 KB.
  - `/api/airport-status-information` (XML): 0.8 s, 2 KB.
- **Fields** (`airport-events`): `airportId, airportLongName, latitude, longitude, groundDelay{avgDelay, maxDelay, impactingCondition, startTime, endTime, advisoryUrl…}, groundStop, arrivalDelay, departureDelay, airportClosure, deicing, freeForm (NOTAMs), airportConfig{arrivalRunwayConfig, departureRunwayConfig, arrivalRate}`.
- At test time: GDPs at BOS (avg 40 min) and DCA; delays at DFW, EWR, PHL, PHX. LAX arrival rate 58/hr (7R/6L), SNA 24/hr (2L).
- **Limitation:** `airportConfig.arrivalRate` only appears when an airport is in the list for some other reason (delay, closure, NOTAM). **SFO was not listed, so there was no live SFO rate.** "Not listed" = no active event, as PLAN says.
- **Fallback for A-10:** reference and reduced rates come from `kb/constraints.yaml` (SFO-02: 54 → 40/hr). The live rate is shown alongside only when present.

## 6. OurAirports — `ourairports.py`

- **Works.** `airports.csv` 12.7 MB / 0.8 s, `runways.csv` 4.0 MB / 0.2 s (GitHub mirror).
- **Fields:** ICAO/IATA codes, `iso_region` (US-MA → state), coordinates, type; runways have `length_ft`, `closed`, `le_ident` / `he_ident`.
- **ICAO mapping works:** ANC → PANC, SFO → KSFO.
- **Effective runways (A-15: open and ≥ 5,000 ft):**

| Airport | Raw | Effective | Note |
|---|---|---|---|
| SNA | 2 | 1 | 2,886 ft GA runway excluded ✅ |
| SFO | 4 | 4 | Geometry handled by KB (SFO-01) ✅ |
| LAX | 4 | 4 | |
| BOS | 6 | 5 | |
| BDL | 3 | 2 | Closed runway excluded ✅ |
| BTV | 2 | 1 | |
| LGA | 3 | 2 | Closed helipad excluded |
| DCA | 3 | 3 | |
| ANC | 3 | 3 | |
| PVD, PWM, MHT | 2 | 2 | |

- **Edge case:** BOS 14/32 and DCA 04/22 are exactly 5,000 ft, so `>=` counts them. This is fine as written; just be aware of it.

## 7. Constraint facts (web research) — `kb/constraints.yaml` updated

- **SNA cap 2026–2030** ([ocair.com key provisions](https://www.ocair.com/about/administration/settlement-agreement/key-provisions-settlement-agreement/)):
  - The cap is **12.2 MAP**, or **12.5 MAP** if 11.21 MAP was served in 2021–2025 *and* certain mitigation measures are met. It was 11.8 MAP through 2025; the agreement ends Dec 31, 2030.
  - No public source found confirms which tier applies in 2026. The county's [2026 allocation report](https://files.ocair.com/media/2025-09/John%20Wayne%20Airport%20Capacity%20Allocations%20for%202026%20Plan%20Year.pdf?VersionId=z8cnQZZgAbzTCMwoZ02OQfO3MKnwN6t9) confirms 95 Class A ADDs through 2030 but gives no MAP number.
  - **The label doesn't depend on it:** SNA passengers (A-07) = 11,180,708, which is 91.6% of 12.2M and 89.4% of 12.5M. Both are ≥ 85%, so Regulatory either way. The KB uses 12.2M and lists 12.5M as the alternative.
  - **Correction to PLAN:** loading bridges have **no limit through 2030**; the cap on them ended in 2020.
- **SNA curfew to 2035:** confirmed by press ([OC Weekly](https://www.ocweekly.com/john-wayne-airport-curfews-remain-through-2035-but-flight-increases-will-come-someday-6455743/)). The hours haven't been checked against the county ordinance (confidence: medium).
- **LAX 78.9M:**
  - It was the Master Plan's **demand forecast**, not a cap ([LAWA Appendix H-4](https://www.lawa.org/media/17454), [LA Business Journal](https://labusinessjournal.com/news/weekly-news/lax-expectations-outpaced-gains/)). Officials say there's no hard cap.
  - LAX handled about 73.7M in 2025 ([LAWA 2025 activity report](https://www.lawa.org/sites/lawa/files/2026-06/2025%20Aviation%20Activity%20Analysis_Final.pdf)). Soft limit confirmed.
- **SFO arrival rate:**
  - The side-by-side landing ban took effect **Mar 31, 2026**; the clear-weather rate fell 54 → 36/hr ([KQED](https://www.kqed.org/news/12078501/sfo-flight-delays-2026-runway-closure-faa-san-francisco-international-aiport-tsa)).
  - Staggered approaches raised it to **40/hr on Aug 12, 2026**, with **42 planned by the end of August** ([Deep Arrival, citing an FAA email via SFGATE](https://deeparrival.com/news/faa-sfo-arrival-rate-increase-staggered-approaches-august-12-2026/)).
  - **Correction to PLAN:** it was 40/42 in August, not "45 in October".
  - Not confirmed in an FAA primary source; confidence: medium.
- **SFO IATA Level 2:** not checked yet; still unverified.

---

## Decisions (Nimrod, 2026-10-17)

| # | Question | Decision | Why |
|---|---|---|---|
| D1 | Which T-100 feed powers the score? | **Socrata summary** for the score; **TranStats route-level** only for route mix (Q3), ULCC share and the cargo-heavy flag (A-20, freighters >= 25% of departures). | The score runs on every question, so it sits on the stable, instant API. TranStats adds the detail only where a question needs it. Freighter distortion at cargo hubs is flagged, not hidden. |
| D2 | How to spot cargo flights? | **TranStats `AIRCRAFT_CONFIG`** gives the exact passenger/cargo split for any month, season or year. OpenSky "last 7 days" reports **all flights, no split**. The callsign list (old A-06a) is **deleted**. | Callsigns missed ~50% of ANC freighters (25.2% vs 11.4% passenger long-haul). Cathay or Korean fly only freighters at ANC but passengers at SFO, so no single list is right everywhere. |
| D3 | Keep NAS delay share in the Airfield rule? | **Keep**, with the caveat "reporting airlines only". | Most direct, measured evidence of runway/ATC congestion. One 5-second download, one division. |
| D4 | How to express lost SFO capacity (A-10)? | **Per hour**: KB rate 54 -> 40 (-14 arrivals/hour), plus the live FAA rate when FAA lists SFO. **No daily extrapolation.** | Two documented numbers and a subtraction; a daily figure would need an operating-hours guess. |
| D5 | SNA cap tier? | Use **12.2M**, mention **12.5M** as unconfirmed. Stop searching. | SNA is Regulatory either way (91.6% vs 89.4% of the cap). |

Applied to: `docs/PLAN.md`, `CLAUDE.md`, `config.yaml` (callsign list removed; A-20 added; OpenSky 2-day request limit), `kb/assumptions.yaml` (A-06, A-10 rewritten; A-06a removed; A-20 added).

**Still open:** SFO IATA Level 2 source; SNA curfew hours against the ordinance.
