---
phase: 05-web-ui-cross-project-polish
plan: "03"
subsystem: cross-project
tags: [sqlite, patterns, cross-db, similarity]

requires:
  - "db_wiki/core/store.py (open_store pattern)"
  - "db_wiki/core/schema.py (current_db_tables, current_db_columns views)"
provides:
  - "open_cross_store() — creates ~/.db-wiki/cross.db with WAL mode"
  - "init_cross_schema() — cross_patterns + cross_db_profiles tables"
  - "push_patterns_to_cross() — extracts naming, enum, schema_shape, state_machine patterns"
  - "get_cross_patterns() — reads patterns with similarity-scaled confidence penalty"
affects:
  - "05-05 (MCP+CLI wiring): will register cross-project export/import commands"

tech-stack:
  added: []
  patterns:
    - "Jaccard similarity for cross-DB confidence penalty (D-09)"
    - "Explicit opt-in pattern sharing (D-07)"

key-files:
  created:
    - db_wiki/cross/__init__.py
    - db_wiki/cross/store.py
    - db_wiki/cross/export.py
    - db_wiki/cross/reader.py
  modified: []

deviations: []
issues: []
---

## What Was Built

Cross-project pattern store enabling knowledge transfer between database projects.

**Store** (`store.py`): Opens `~/.db-wiki/cross.db` with WAL mode, creates `cross_patterns` (naming conventions, enum values, schema shapes, state machines) and `cross_db_profiles` (per-DB fingerprints for similarity calculation).

**Export** (`export.py`): `push_patterns_to_cross()` extracts 4 pattern types from the knowledge store — column naming conventions (suffix/prefix detection), enum value sets, schema shapes (audit columns, soft delete, polymorphic), and state machine transitions. Only called when user explicitly opts in (D-07).

**Reader** (`reader.py`): `get_cross_patterns()` returns patterns with similarity-scaled confidence penalty per D-09. Uses Jaccard similarity on table name sets: identical schemas get 20% penalty, completely different schemas get 70% penalty. Results include original and adjusted confidence plus similarity score.

## Self-Check: PASSED

- [x] open_cross_store() creates cross.db with WAL mode
- [x] init_cross_schema() creates cross_patterns and cross_db_profiles tables
- [x] push_patterns_to_cross() extracts all 4 pattern types
- [x] get_cross_patterns() applies similarity-scaled confidence penalty
- [x] All functions importable from db_wiki.cross.*
