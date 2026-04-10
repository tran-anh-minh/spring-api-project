---
plan: 02-03
phase: 02-sp-parsing-knowledge-graph
status: complete
started: "2026-04-10"
completed: "2026-04-10"
duration: ~11 min
commits: 4
tests_added: 24
tests_total: 145
regressions: 0
---

# Plan 02-03 Summary: Search Infrastructure

## What Was Built

Lazy-loaded embedding via sentence-transformers, FTS5 full-text indexing, and hybrid score fusion search. Three modules in `db_wiki/search/`:

1. **Embedder** (`embedder.py`) — Lazy-loaded sentence-transformers with sqlite-vec integration. Supports `local` (all-MiniLM-L6-v2, 384-dim) and `openai` (text-embedding-3-small, 1536-dim) providers. `ensure_ready()` defers torch import until first use. Methods: `encode()`, `embed_entities()`, `search_similar()`.

2. **FTS5** (`fts.py`) — Full-text search over entity names/descriptions. `populate_fts()` inserts records, `search_fts()` returns ranked matches, `sync_fts()` clears and repopulates, `populate_fts_from_store()` auto-populates from tables and procedures.

3. **Hybrid Search** (`hybrid.py`) — Score fusion combining vector similarity and FTS5 keyword matches. `fuse_scores()` merges results with configurable `vec_weight` (default 0.6). `hybrid_search()` orchestrates both backends with FTS-only fallback when embedder unavailable.

## Key Files

### Created
- `db_wiki/search/__init__.py` — Package init
- `db_wiki/search/embedder.py` — Lazy-loaded Embedder class
- `db_wiki/search/fts.py` — FTS5 index management
- `db_wiki/search/hybrid.py` — Hybrid score fusion
- `tests/test_search.py` — 24 tests covering all search behaviors

### Modified
- `pyproject.toml` — Added `sentence-transformers` and `openai` as optional dependencies

## Commits
1. `ef62d4b` — test(02-03): add failing tests for Embedder and serialize_embedding
2. `91ae7f0` — feat(02-03): implement lazy-loaded Embedder with sqlite-vec integration
3. `73b22a3` — test(02-03): add failing tests for FTS5 and hybrid search
4. `d3ac972` — feat(02-03): FTS5 index and hybrid score fusion search

## Test Results

24 new tests, 145 total passing, 0 regressions.

## Deviations

None — implemented as planned.

## Self-Check: PASSED
- [x] All tasks executed (2/2)
- [x] Each task committed individually
- [x] SUMMARY.md created
- [x] All tests passing
- [x] No regressions
