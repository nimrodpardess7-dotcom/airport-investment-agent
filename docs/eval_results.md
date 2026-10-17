# Eval results

8/8 cases passed · total cost $0.42 · model claude-opus-5-5 · run 2026-10-17

Graded in code: required tools called, required facts/caveats present (regex), clean grounding check.

| Case | Result | Tools called (last turn) | Failed checks | Time |
|---|---|---|---|---|
| q1_new_england | ✅ pass | rank_airports | - | 16 s |
| q2_lax_vs_sna | ✅ pass | compare_airports | - | 17 s |
| q3_anc_long_haul | ✅ pass | route_mix, route_mix | - | 15 s |
| q4_sfo_unmet_demand | ✅ pass | demand_signals, get_constraints | - | 15 s |
| followup_memory | ✅ pass | compare_airports, demand_signals, get_constraints | - | 31 s |
| what_if_weights | ✅ pass | rank_airports | - | 32 s |
| ambiguous_name | ✅ pass | none | - | 3 s |
| unanswerable | ✅ pass | get_constraints, compare_airports | - | 12 s |
