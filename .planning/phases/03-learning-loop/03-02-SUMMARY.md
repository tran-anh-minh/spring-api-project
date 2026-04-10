---
phase: 03-learning-loop
plan: 02
subsystem: learning
tags: [gap-detection, gap-scoring, discover-phase, learning-loop]
dependency_graph:
  requires: [03-01]
  provides: [gap_detector, gap_scorer]
  affects: [learning-loop-orchestrator]
tech_stack:
  added: []
  patterns: [sqlite-parameterized-queries, bfs-connectivity, weighted-scoring-formula]
key_files:
  created:
    - db_wiki/learning/gap_scorer.py
    - tests/test_gap_scorer.py
  modified: []
decisions:
  - gap_recorded_at_ts=0 means new gap with staleness=0 (age_days / 30 formula)
  - connectivity fallback to 0.0 on bfs_graph failure via try/except
  - query_frequency defaults to 0.5 neutral until Phase 4 adds query logs
metrics:
  duration: 8m
  completed_date: "2026-04-10"
  tasks_completed: 2
  files_changed: 2
---

# Phase 03 Plan 02: Gap Detector and Gap Scorer Summary

**One-liner:** 12-rule gap detector + D-12 weighted scoring formula (severity*0.3 + connectivity*0.25 + query_freq*0.20 + staleness*0.15 + solvability*0.10) for the learning loop Discover phase.

## What Was Built

### Task 1 (pre-completed): Gap Detector — `db_wiki/learning/gap_detector.py`

12 detection rules implemented as parameterized SQL queries against Phase 2 `current_*` views:

1. `detect_unlabeled_enums` — enum_values with NULL/empty label (severity 0.7)
2. `detect_orphan_tables` — tables with no relationships (severity 0.5)
3. `detect_missing_joins` — joins_with relationships with no FK evidence (severity 0.6)
4. `detect_stale_facts` — low-confidence enum values older than threshold (severity 0.4)
5. `detect_alias_clusters` — column aliases with ambiguous multiple entries (severity 0.3)
6. `detect_incomplete_state_machines` — state columns with fewer than 2 distinct transitions (severity 0.6)
7. `detect_unresolved_calls` — SP call chains where callee is unresolved (severity 0.5)
8. `detect_low_confidence_facts` — facts below confidence threshold across 3 tables (severity 0.4)
9. `detect_cross_sp_contradictions` — same enum value with conflicting labels (severity 0.8)
10. `detect_missing_fks` — _id/_code columns without FK relationship (severity 0.6)
11. `detect_coverage_gaps` — tables/SPs with NULL description (severity 0.3)
12. `detect_pattern_anomalies` — SPs with low parse quality or degraded AST (severity 0.4)

`detect_all_gaps()` aggregates all 12 rules. `upsert_gaps()` handles deduplication with cooldown and permanent-status respect.

### Task 2: Gap Scorer — `db_wiki/learning/gap_scorer.py`

- `score_gap(conn, gap, weights, gap_recorded_at_ts)` — computes D-12 formula, returns float in [0.0, 1.0]
- `score_and_prioritize(conn, config)` — scores all open gaps, persists priority_score, returns top-N sorted DESC
- `get_eligible_gaps(conn, max_gaps, now_ts)` — returns open gaps with expired/no cooldown, ordered by priority_score DESC
- `SOLVABLE_WITH_SAMPLING` set drives the solvability dimension

## Test Coverage

- `tests/test_gap_detector.py`: 20 tests — all 12 rules, aggregate, upsert dedup logic
- `tests/test_gap_scorer.py`: 14 tests — score formula, sorting, limits, cooldown filtering, SOLVABLE_WITH_SAMPLING constant

All 34 tests pass.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

- `query_frequency = 0.5` (neutral default) in `score_gap()` — Phase 4 will wire real query log counts.

## Self-Check: PASSED

- `db_wiki/learning/gap_scorer.py` — FOUND
- `tests/test_gap_scorer.py` — FOUND
- Commit `02f1651` — FOUND (feat(03-02): implement gap priority scoring formula)
