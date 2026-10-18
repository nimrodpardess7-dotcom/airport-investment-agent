# Eval results

8/8 cases passed · total cost $0.28 · model claude-opus-5-5 · run 2026-10-18

Graded in code: required tools called, required facts/caveats present (regex), clean grounding check.

| Case | Result | Tools called (last turn) | Failed checks | Time |
|---|---|---|---|---|
| q1_new_england | ✅ pass | rank_airports | - | 15 s |
| q2_lax_vs_sna | ✅ pass | compare_airports | - | 12 s |
| q3_anc_long_haul | ✅ pass | route_mix | - | 13 s |
| q4_sfo_unmet_demand | ✅ pass | demand_signals, get_constraints | - | 12 s |
| followup_memory | ✅ pass | demand_signals, get_constraints | - | 26 s |
| what_if_weights | ✅ pass | rank_airports | - | 28 s |
| ambiguous_name | ✅ pass | none | - | 2 s |
| unanswerable | ✅ pass | get_constraints, compare_airports | - | 11 s |
