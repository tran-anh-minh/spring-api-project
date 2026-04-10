# DB Wiki — Research Report

## 1. Concerns

### 1.1 User Concerns

| # | Concern | Why It's Hard |
|---|---------|---------------|
| **C1** | **Can't learn everything in one pass** | Thousands of SPs, undocumented enums, implicit relationships — needs hundreds of iterations to reach deep understanding |
| **C2** | **Need a loop to upgrade memory** | Knowledge compounds: pass N+1 uses what pass N learned to find deeper patterns |
| **C3** | **Auto-find gaps** | The tool must know what it doesn't know — missing labels, unexplained tables, weak relationships |
| **C4** | **Auto-fix conflict logic** | SPs may be wrong, outdated, or contradictory. Column names duplicated. Aliases everywhere |
| **C5** | **Undocumented enum values** | GameMode=1-20, Status=0-9 — no docs, must infer from SP names, CASE statements, data sampling, human confirmation |
| **C6** | **Easy setup (MCP install)** | No Neo4j cluster, no Docker complexity — install like a package, point at database |
| **C7** | **Natural language → exact SQL** | "Get tournaments by store in USA" must produce correct JOIN path, correct column names, correct filter values |
| **C8** | **Cross-project knowledge** | Learnings from database A should inform understanding of database B (shared patterns, naming conventions) |

### 1.2 Architecture Concerns (Gaps Found During Role-Based Stress Testing)

| # | Concern | Why No Existing Tool Solves It | Found By |
|---|---------|-------------------------------|----------|
| **M1** | **SQL AST parsing at scale** | All memory tools are text-based. None parse SQL syntax trees to extract JOINs, WHERE clauses, INSERT...SELECT lineage | Initial analysis |
| **M2** | **Schema-aware entity resolution** | Mem0/Graphiti extract entities from text. We need to extract from DDL + SP code — different extraction logic | Initial analysis |
| **M3** | **Confidence from multiple evidence sources** | Existing tools: confidence = embedding similarity. We need: confidence = f(SP count, data sampling, human confirmation, recency) | Initial analysis |
| **M4** | **Proactive gap detection** | All existing tools are reactive (learn when new data arrives). We need proactive: "I have 340 enum columns, 89 are labeled → investigate the other 251" | Initial analysis |
| **M5** | **Data sampling integration** | No existing tool runs SELECT DISTINCT to verify hypotheses. We need live DB access for validation | Initial analysis |
| **M6** | **Bitmask vs enum detection** | No tool distinguishes `Flags & 4 = 4` (bitmask) from `Status = 4` (enum). Requires SQL AST analysis | Initial analysis |
| **M7** | **SP reliability scoring** | If SP-A and SP-B contradict, which is right? Need: execution frequency, last modified, error logs, caller count | Initial analysis |
| **M8** | **Zero-infrastructure requirement** | Most graph memory tools need Neo4j. We need SQLite-only for easy MCP install | Initial analysis |
| **M9** | **SP control flow analysis** | sqlglot parses data flow (tables, JOINs) but not logic flow (IF/ELSE branches, variable assignments, WHILE loops) | Tester T3, T2 |
| **M10** | **State machine extraction** | Labeling enum values ≠ understanding transitions. Need to extract `UPDATE SET Status=X WHERE Status=Y` patterns across all SPs to build transition graphs | Tester T2 |
| **M11** | **Analytical query generation** | Architecture only generates lookup queries (SELECT+JOIN+WHERE). BA/CS need GROUP BY, window functions, CTEs, statistical calculations | BA1, BA2, CS2 |
| **M12** | **Derived metric knowledge** | "Churn", "lifetime value", "downgrade" are business concepts not stored in columns. Engine needs teachable business concept → SQL mappings | BA1, CS2 |
| **M13** | **Negative knowledge / coverage analysis** | Engine reports what exists but not what's missing. BA needs "what SHOULD we track but don't?" | BA3 |
| **M14** | **Dynamic SQL and triggers** | Many legacy SPs build SQL via `EXEC(@sql)`. State changes via triggers/jobs invisible to SP-only parsing | Dev D2, Tester T2 |
| **M15** | **Temporal forensics** | "What changed for customer X in the last 48 hours?" requires knowing which tables have audit timestamps, history tables, change tracking | CS1 |
| **M16** | **Data quality queries** | Finding broken FK references, impossible values, orphan records — queries that specifically look for data inconsistencies | Tester T1 |

---

## 2. Existing Tools Analyzed

### 2.1 codebase-memory-mcp (DeusData)

**What it does well:**
- Graph storage in SQLite — 2.1M nodes, 4.9M edges for Linux kernel in 3 minutes
- 13 node types, 18 edge types, Cypher-like queries
- BFS traversal with depth control (1-5 hops)
- Auto-sync on file changes
- CLI + MCP dual mode

**What it doesn't solve for us:**
- Designed for **code** (Class, Function, Method nodes), not **database schemas** (Table, Column, SP, Enum)
- No SQL parsing — can't extract JOINs from stored procedures
- No confidence scoring — everything is a fact, no "maybe" state
- No learning loop — indexes once, doesn't deepen understanding over iterations
- No enum/value discovery
- No contradiction detection

**Verdict:** Steal the architecture (SQLite graph + BFS), rebuild the node/edge types for database domain.

### 2.2 claude-mem (thedotmack)

**What it does well:**
- 5 lifecycle hooks for automatic capture
- Progressive disclosure (search → timeline → detail) — 10x token efficiency
- Observation-based architecture — captures what happened, summarizes later
- Hybrid search: Chroma vectors + SQLite FTS5

**What it doesn't solve for us:**
- General-purpose session memory, not domain-specific knowledge
- No entity extraction or relationship building
- No gap detection or learning loop
- No schema understanding

**Verdict:** Steal the progressive disclosure pattern and hook-based auto-capture. The observation → summarization pipeline is good for the episodic memory tier.

### 2.3 Mem0

**What it does well:**
- **Two-phase pipeline**: Extraction (entity + relation triplets) → Update (ADD/UPDATE/DELETE/NOOP)
- **Graph memory variant (Mem0^g)**: Entities + typed relationships in Neo4j
- **Conflict detection**: Embedding similarity (threshold ≥ 0.7) + LLM resolver
- **Temporal priority**: "If contradictory, prioritize most recent"
- **Benchmark-proven**: 26% improvement over OpenAI baseline, 91% lower p95 latency
- **Token efficient**: ~7k tokens/conversation vs 600k+ for full-context

**What it doesn't solve for us:**
- Requires Neo4j (heavy infrastructure) for graph variant
- Designed for **conversational** memory, not **structural** database knowledge
- No SQL parsing pipeline
- No data sampling / enum discovery
- No gap detection loop — reacts to new data, doesn't proactively seek
- Conflict resolution is per-conversation, not per-domain

**Verdict:** The extraction → update pipeline with 4-operation framework (ADD/UPDATE/DELETE/NOOP) is the right model for our knowledge updates. The conflict detection via embedding similarity + LLM resolver is directly applicable. But we need to replace Neo4j with SQLite and add domain-specific extraction.

### 2.4 Graphiti / Zep

**What it does well:**
- **Bi-temporal model**: Tracks both "when true in reality" and "when recorded" — perfect for versioned SPs
- **Fact invalidation, not deletion**: Old facts preserved with validity windows — critical for tracking SP evolution
- **Episode-based provenance**: Every fact traces to source episodes (for us: which SPs proved this relationship)
- **Entity deduplication**: Automatic across episodes
- **Hybrid search**: Semantic + BM25 + graph traversal
- **Sub-second queries** at P95

**What it doesn't solve for us:**
- Requires Neo4j 5.26+ (infrastructure overhead)
- LLM-dependent extraction (expensive for thousands of SPs)
- No domain-specific SQL parsing
- No gap detection or proactive investigation loop

**Verdict:** The bi-temporal model is the **single most important insight** for our tool. Database knowledge changes — SPs get updated, tables get renamed, columns get added. We must track when a fact was true and when we learned it. Steal this model, implement in SQLite.

### 2.5 OpenViking (ByteDance)

**What it does well:**
- **Tiered context loading (L0/L1/L2)**: One-sentence abstract → structured overview → full detail. Only loads what's needed
- **Virtual filesystem (viking:// protocol)**: Everything addressable as URI
- **Hierarchical context**: Not flat chunks — preserves structure

**What it doesn't solve for us:**
- Context management, not knowledge building — it organizes what you give it, doesn't learn new things
- No extraction, no graph, no learning loop

**Verdict:** The L0/L1/L2 tiered loading is critical for token efficiency when querying. When Claude asks about a table, give L0 (name + purpose) for 200 tables, L1 (columns + relationships) for 10 relevant tables, L2 (full wiki page + SP evidence) for the 2 most relevant. Steal this pattern.

### 2.6 LangGraph + LangChain

**What it does well:**
- **Self-correcting RAG loops**: Query → retrieve → grade → rewrite → retry
- **Directed cyclic graphs**: Perfect for modeling our learning loop
- **Checkpointing**: Save/resume state between runs
- **Human-in-the-loop**: Interruptible at any point for confirmation

**What it doesn't solve for us:**
- Framework, not solution — we'd build on top of it
- Heavy dependency chain (LangChain ecosystem)
- Overkill for MCP tool that should be lightweight

**Verdict:** The self-correcting loop pattern (retrieve → grade → decide → retry/escalate) is exactly what we need for gap detection. But implement it as simple Python state machine, not full LangGraph — keeps the tool lightweight and MCP-friendly.

### 2.7 Cognee

**What it does well:**
- **Continuous learning**: Learns from feedback, tracks outcomes
- **Auto-correction**: Reconstructs timeline, retrieves similar resolved cases, updates memory
- **Cross-agent knowledge sharing**: Multiple AI agents share one knowledge base
- **MCP integration**: Built-in MCP server

**What it doesn't solve for us:**
- General-purpose semantic memory, not database-domain specific
- No SQL parsing
- No enum discovery

**Verdict:** The auto-correction pattern (track outcomes → match to similar cases → update strategy) is directly applicable to our conflict resolution. If SP-A says X but query results contradict X, learn that SP-A is unreliable.

---

## 3. Architecture

### 3.1 Design Inspirations

```
┌─────────────────────────────────────────────────────────────┐
│                    FROM EACH TOOL WE TAKE                    │
├─────────────────────────────────────────────────────────────┤
│ codebase-memory-mcp  → SQLite graph + BFS traversal engine  │
│ claude-mem           → Progressive disclosure + hooks        │
│ Mem0                 → 4-op update pipeline + conflict detect│
│ Graphiti/Zep         → Bi-temporal model + fact invalidation │
│ OpenViking           → L0/L1/L2 tiered context loading      │
│ LangGraph            → Self-correcting loop pattern          │
│ Cognee               → Outcome tracking + auto-correction    │
│ Karpathy LLM Wiki   → Wiki compilation + lint operations     │
│ LLM Wiki v2          → Confidence decay + memory tiers       │
├─────────────────────────────────────────────────────────────┤
│                    WE ADD (novel)                             │
├─────────────────────────────────────────────────────────────┤
│ sqlglot              → SQL AST parsing for SP analysis       │
│ Domain entity types  → Table/Column/SP/Enum/Relationship     │
│ Data sampling engine → Live DB queries to verify hypotheses  │
│ Gap priority queue   → Proactive investigation scheduling    │
│ SP reliability score → Which stored procedures to trust      │
│ SP control flow      → IF/ELSE branch extraction from SPs   │
│ State machine extract→ Transition graphs from UPDATE patterns│
│ Query tier system    → Lookup/Aggregate/Temporal/Statistical │
│ Derived metrics      → Teachable business concept→SQL map    │
│ Domain templates     → Coverage analysis for missing schema  │
│ Audit discovery      → Find timestamp/history/tracking cols  │
│ Data quality engine  → Orphan FK, impossible values, dupes   │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Full System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        LAYER 1: INGEST                           │
│                                                                   │
│  Source Parsers                                                   │
│  ├── DDL Parser                                                  │
│  │   └── tables, columns, constraints, indexes                   │
│  ├── SP Parser (sqlglot AST)                                     │
│  │   ├── Data flow: tables, columns, JOINs, mutations            │
│  │   ├── Control flow: IF/ELSE branches, CASE, variable tracking │
│  │   ├── State transitions: UPDATE SET col=X WHERE col=Y         │
│  │   ├── Call chains: SP-A calls SP-B calls SP-C                 │
│  │   └── Dynamic SQL: detect EXEC(@sql), flag as opaque          │
│  ├── Trigger Parser                                              │
│  │   └── AFTER/INSTEAD OF triggers → same analysis as SP         │
│  ├── SQL Agent Job Parser                                        │
│  │   └── scheduled job steps → same analysis as SP               │
│  └── Metadata Extractor                                          │
│      ├── sys.columns, sys.types → column stats                   │
│      ├── sys.dm_exec_procedure_stats → SP execution frequency    │
│      ├── sys.triggers → trigger inventory                        │
│      └── msdb.dbo.sysjobs → scheduled job inventory              │
│                                                                   │
│  Each parser produces evidence records with:                     │
│  - source (which SP/DDL/trigger)                                 │
│  - extraction_type (join, mutation, branch, transition, etc.)    │
│  - confidence (how certain the extraction is)                    │
│  - timestamp (when extracted)                                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 2: KNOWLEDGE STORE                      │
│                                                                   │
│  SQLite Database (single file, zero infrastructure)              │
│                                                                   │
│  Core Entities                                                   │
│  ├── db_tables (name, schema, description, row_count_est)        │
│  ├── db_columns (table_id, name, type, nullable, description)    │
│  ├── db_procedures (name, body_hash, description, reliability)   │
│  ├── db_triggers (name, table_id, event_type, body_hash)         │
│  └── db_jobs (name, schedule, description)                       │
│                                                                   │
│  Relationships                                                   │
│  ├── db_relationships                                            │
│  │   (src_table, src_col, dst_table, dst_col, rel_type,         │
│  │    confidence, evidence[], first_seen, last_confirmed)        │
│  │   rel_types: fk_declared, fk_inferred, joins_with,           │
│  │              reads_from, writes_to, feeds_into                │
│  └── sp_call_chains (caller_sp, callee_sp, call_context)        │
│                                                                   │
│  Value Intelligence                                              │
│  ├── enum_values                                                 │
│  │   (table, column, raw_value, label, confidence,               │
│  │    confirmed_by, evidence[])                                  │
│  ├── bitmask_definitions                                         │
│  │   (table, column, bit_position, label, confidence)            │
│  ├── state_transitions                                           │
│  │   (table, column, from_value, to_value, sp_name,             │
│  │    condition, is_backward, confidence)                        │
│  └── column_aliases                                              │
│      (canonical_name, alias_name, table_name, confidence)        │
│                                                                   │
│  Business Intelligence                                           │
│  ├── derived_metrics                                             │
│  │   (metric_name, definition, required_tables,                  │
│  │    sql_definition, confirmed_by, confidence)                  │
│  ├── domain_templates                                            │
│  │   (domain, touchpoint_name, expected_tables,                  │
│  │    expected_columns, coverage_status)                         │
│  └── query_templates                                             │
│      (tier, intent_pattern, sql_template,                        │
│       required_columns, example_question)                        │
│                                                                   │
│  Audit Infrastructure                                            │
│  ├── audit_capabilities                                          │
│  │   (table, has_change_timestamp, timestamp_col,                │
│  │    has_history_table, history_table_name,                     │
│  │    is_system_versioned)                                       │
│  └── data_quality_rules                                          │
│      (table, column, check_type, expected, actual,               │
│       severity, last_checked)                                    │
│                                                                   │
│  Knowledge Lifecycle (bi-temporal, from Graphiti)                 │
│  ├── knowledge_facts                                             │
│  │   (entity_type, entity_id, fact_text,                         │
│  │    valid_from, valid_until,        ← when true in reality     │
│  │    recorded_at, invalidated_at,    ← when we learned it       │
│  │    confidence, confidence_history,                             │
│  │    evidence_sources, confirmed_by,                            │
│  │    supersedes_id, superseded_by_id)                           │
│  └── knowledge_gaps                                              │
│      (entity_type, entity_name, gap_type, severity,              │
│       attempts, last_attempt, status, auto_resolution,           │
│       confidence)                                                │
│                                                                   │
│  Wiki Pages (Karpathy pattern)                                   │
│  ├── wiki_pages (slug, title, content_md, tier,                  │
│  │               confidence, version, supersedes_id)             │
│  │   tier: L0 (one-line), L1 (structured), L2 (full detail)     │
│  └── wiki_facts (page_id, fact_text, sources, confidence)        │
│                                                                   │
│  Search Infrastructure                                           │
│  ├── chunk_vec (sqlite-vec, 512-d embeddings)                    │
│  ├── wiki_fts (FTS5 full-text search)                            │
│  └── rel_graph (bfsvtab BFS graph traversal)                     │
│                                                                   │
│  Cross-Project (separate file: ~/.db-wiki/cross.db)  │
│  ├── naming_patterns (pattern, meaning, seen_in_projects)        │
│  ├── common_enums (column_pattern, values, frequency)            │
│  └── schema_patterns (pattern_name, structure, frequency)        │
│                                                                   │
│  SP Intelligence                                                 │
│  ├── sp_branches                                                 │
│  │   (sp_id, branch_id, condition, tables_read,                  │
│  │    tables_written, status_changes, nesting_depth)             │
│  ├── sp_reliability                                              │
│  │   (sp_id, score, last_modified, execution_count,              │
│  │    caller_count, has_dynamic_sql, has_error_handling,         │
│  │    contradiction_count, is_deprecated)                        │
│  └── sp_transaction_scope                                        │
│      (sp_id, has_explicit_transaction, tables_in_transaction,    │
│       isolation_level, deadlock_risk_tables)                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 3: LEARNING LOOP                         │
│                                                                   │
│  Five-phase continuous improvement cycle                         │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  Phase 1: DISCOVER — "what don't I know?"               │     │
│  │                                                          │     │
│  │  Gap Detection Rules:                                    │     │
│  │  ├── Unlabeled enums: int columns, low cardinality,     │     │
│  │  │   no labels, no FK to lookup table                    │     │
│  │  ├── Unknown bitmasks: columns used with & | operators   │     │
│  │  ├── Orphan tables: not referenced by any SP/trigger     │     │
│  │  ├── Missing join paths: tables co-appear in SPs but     │     │
│  │  │   no recorded relationship                            │     │
│  │  ├── Stale facts: confidence decayed, not confirmed      │     │
│  │  │   recently                                            │     │
│  │  ├── Alias clusters: multiple names for same entity      │     │
│  │  ├── Incomplete state machines: transitions with          │     │
│  │  │   missing from/to values                              │     │
│  │  ├── Undescribed tables/columns: no wiki page yet        │     │
│  │  ├── Suspicious SPs: contradictions with other SPs       │     │
│  │  ├── Audit blind spots: tables with no timestamp cols    │     │
│  │  ├── Data quality unknowns: columns never sampled        │     │
│  │  └── Derived metric gaps: business concepts mentioned    │     │
│  │      in queries but no SQL definition stored             │     │
│  │                                                          │     │
│  │  Priority scoring:                                       │     │
│  │    severity_weight × 0.3                                 │     │
│  │  + connectivity_score × 0.25                             │     │
│  │  + user_query_frequency × 0.20                           │     │
│  │  + staleness_score × 0.15                                │     │
│  │  + solvability_score × 0.10                              │     │
│  └─────────────────────────────────────────────────────────┘     │
│                         │ top-N gaps                              │
│                         ▼                                        │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  Phase 2: INVESTIGATE — "gather evidence"               │     │
│  │                                                          │     │
│  │  Evidence sources (by gap type):                         │     │
│  │  ├── For unknown enums:                                  │     │
│  │  │   ├── CASE statements in SPs                         │     │
│  │  │   ├── SP names containing value hints                │     │
│  │  │   ├── SELECT DISTINCT from live DB                   │     │
│  │  │   ├── Cross-reference with other columns             │     │
│  │  │   └── Cross-project common enum patterns             │     │
│  │  ├── For missing relationships:                          │     │
│  │  │   ├── Column name pattern matching                   │     │
│  │  │   ├── Data type + value range overlap                │     │
│  │  │   ├── SP JOIN clause evidence                        │     │
│  │  │   └── INSERT...SELECT data flow                      │     │
│  │  ├── For suspicious SPs:                                 │     │
│  │  │   ├── Compare SP output vs expected from schema      │     │
│  │  │   ├── Check execution frequency (dead code?)         │     │
│  │  │   ├── Check last modified date                       │     │
│  │  │   └── Check if called by other SPs                   │     │
│  │  ├── For audit blind spots:                              │     │
│  │  │   ├── Scan column names for timestamp patterns       │     │
│  │  │   ├── Check for *_History, *_Log sibling tables      │     │
│  │  │   ├── Check sys.tables for temporal_type             │     │
│  │  │   └── Check triggers for audit logging               │     │
│  │  └── For dynamic SQL:                                    │     │
│  │      ├── Try static resolution (trace @var assignments) │     │
│  │      ├── Execute with profiler to capture actual SQL    │     │
│  │      └── Flag as opaque if unresolvable                 │     │
│  └─────────────────────────────────────────────────────────┘     │
│                         │ evidence bundles                        │
│                         ▼                                        │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  Phase 3: REASON — "connect the dots"                   │     │
│  │                                                          │     │
│  │  4-Operation Update Pipeline (adapted from Mem0):        │     │
│  │  ├── ADD: new information, no existing fact              │     │
│  │  ├── REINFORCE: same conclusion from new source          │     │
│  │  │   → boost confidence, add evidence source             │     │
│  │  ├── CONFLICT: new evidence contradicts existing         │     │
│  │  │   Resolution strategies:                              │     │
│  │  │   ├── SUPERSEDE: new is more trustworthy              │     │
│  │  │   │   (invalidate old fact, bi-temporal tracking)     │     │
│  │  │   ├── KEEP: existing is more trustworthy              │     │
│  │  │   │   (log new evidence, lower its confidence)        │     │
│  │  │   ├── SPLIT: both true in different contexts          │     │
│  │  │   │   (e.g., Status=1 means diff things per table)   │     │
│  │  │   └── ESCALATE: can't decide → ask human             │     │
│  │  └── NOOP: evidence doesn't change anything              │     │
│  │                                                          │     │
│  │  Conflict Resolution Scoring:                            │     │
│  │  new_score = sp_reliability × 0.25                       │     │
│  │            + recency × 0.20                              │     │
│  │            + usage_frequency × 0.15                      │     │
│  │            + evidence_count × 0.15                       │     │
│  │            + data_validation × 0.25                      │     │
│  │                                                          │     │
│  │  existing_score = accumulated_confidence × 0.30          │     │
│  │                 + human_confirmed × 0.40                 │     │
│  │                 + evidence_count × 0.15                  │     │
│  │                 + recency × 0.15                         │     │
│  │                                                          │     │
│  │  Rule: NEVER override human confirmation without asking  │     │
│  │                                                          │     │
│  │  SP Reliability Scoring:                                 │     │
│  │  baseline = 0.5                                          │     │
│  │  + 0.10 if recently modified (< 1 year)                  │     │
│  │  + 0.10 if heavily used (execution_count > 1000)         │     │
│  │  + 0.10 if called by other SPs                           │     │
│  │  + 0.05 if no dynamic SQL                                │     │
│  │  + 0.05 if has error handling                            │     │
│  │  - 0.15 if name contains 'old', 'bak', 'legacy'         │     │
│  │  - 0.10 if has contradictions with other SPs             │     │
│  │  - 0.10 if never executed (dead code)                    │     │
│  │  - 0.05 if has commented-out code                        │     │
│  └─────────────────────────────────────────────────────────┘     │
│                         │ proposed changes                        │
│                         ▼                                        │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  Phase 4: VALIDATE — "am I right?"                      │     │
│  │                                                          │     │
│  │  Self-Consistency Checks:                                │     │
│  │  ├── Relationship symmetry: if A→B then B should        │     │
│  │  │   co-appear with A in SPs                            │     │
│  │  ├── Enum completeness: DISTINCT values vs known labels │     │
│  │  ├── Circular relationships: flag cycles > 3 hops       │     │
│  │  ├── Alias consistency: same data type + value range    │     │
│  │  │   across all aliases                                 │     │
│  │  ├── SP output validation: run SP, compare result       │     │
│  │  │   columns with wiki understanding                    │     │
│  │  ├── State machine completeness: all data values have   │     │
│  │  │   incoming transition                                │     │
│  │  ├── State machine anomalies: backward transitions,     │     │
│  │  │   skipped states, orphan states, dead-end states     │     │
│  │  ├── Cross-table column consistency: same-named columns │     │
│  │  │   have compatible types and ranges                   │     │
│  │  └── Data quality spot checks: sample N rows, verify    │     │
│  │      FK references resolve, values within expected range│     │
│  │                                                          │     │
│  │  If confidence < threshold → ESCALATE to human           │     │
│  │  Human confirmation → confidence = 1.0, confirmed_by =  │     │
│  │  'human'                                                 │     │
│  └─────────────────────────────────────────────────────────┘     │
│                         │ validated changes                       │
│                         ▼                                        │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  Phase 5: CONSOLIDATE — "update & plan next"            │     │
│  │                                                          │     │
│  │  ├── Apply changes with bi-temporal tracking             │     │
│  │  │   (valid_from/until + recorded_at/invalidated_at)    │     │
│  │  ├── Supersede old facts (mark superseded_by, don't     │     │
│  │  │   delete — preserve history)                         │     │
│  │  ├── Update wiki pages (L0/L1/L2 tiers)                 │     │
│  │  ├── Update confidence scores across affected entities  │     │
│  │  ├── Promote episodic → semantic memory                  │     │
│  │  │   (session findings → permanent knowledge)           │     │
│  │  ├── Generate NEW gaps from what was learned             │     │
│  │  │   (discovering table X reveals 5 unknown columns)    │     │
│  │  ├── Update cross-project patterns if applicable         │     │
│  │  ├── Update maturity score                               │     │
│  │  └── Log operation to append-only audit trail            │     │
│  └─────────────────────────────────────────────────────────┘     │
│                         │                                        │
│                         └──→ next loop iteration                 │
│                                                                   │
│  Loop Scheduling:                                                │
│  ├── fast_loop (every ingest/query):                             │
│  │   update confidence, detect conflicts, flag gaps              │
│  ├── medium_loop (daily / on-demand):                            │
│  │   sample data for top-20 gaps, merge aliases, auto-resolve    │
│  ├── deep_loop (weekly / on-demand):                             │
│  │   bitmask scan, duplicate detection, SP validation,           │
│  │   consolidate tiers, knowledge report                         │
│  └── human_loop (when stuck):                                    │
│      present unresolvable gaps with evidence, ask specific Qs    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 4: QUERY ENGINE                          │
│                                                                   │
│  Query Complexity Tiers:                                         │
│  ├── Tier 1: Lookup                                              │
│  │   SELECT + JOIN + WHERE + ORDER BY                            │
│  │   "get all tournaments by store in USA"                       │
│  │                                                                │
│  ├── Tier 2: Aggregation                                         │
│  │   GROUP BY + aggregate functions + HAVING                     │
│  │   "total orders per customer per month"                       │
│  │                                                                │
│  ├── Tier 3: Temporal                                            │
│  │   Window functions (LAG, LEAD, ROW_NUMBER)                    │
│  │   Date range comparisons, period-over-period                  │
│  │   "customers whose order value declined 3 months in a row"   │
│  │                                                                │
│  ├── Tier 4: Statistical                                         │
│  │   AVG + STDEV + percentiles, z-score, cohort comparison      │
│  │   "stores with scores 2+ stdev above average"                │
│  │                                                                │
│  ├── Tier 5: Forensic                                            │
│  │   UNION across auditable tables with timestamps               │
│  │   Before/after comparison, change delta                       │
│  │   "everything that changed for customer X this week"          │
│  │                                                                │
│  └── Tier 6: Data Quality                                        │
│      Orphan FK detection, impossible values, NULL analysis       │
│      Duplicate detection, constraint violation scan              │
│      "find orders with broken references or negative totals"    │
│                                                                   │
│  Query Generation Pipeline:                                      │
│  ├── 1. Concept Resolution                                       │
│  │      NL terms → schema entities via hybrid search             │
│  │      (vector similarity + FTS5 keyword + wiki lookup)         │
│  │      "tournament" → dbo.Tournaments (confidence: 0.95)        │
│  │                                                                │
│  ├── 2. Derived Metric Resolution                                │
│  │      Business terms → stored SQL definitions                  │
│  │      "churned customers" → derived_metrics.churn              │
│  │                                                                │
│  ├── 3. Relationship Path Finding                                │
│  │      BFS graph traversal to find JOIN paths                   │
│  │      Between resolved tables, shortest + highest confidence   │
│  │                                                                │
│  ├── 4. Tier Classification                                      │
│  │      Analyze intent → select query complexity tier            │
│  │      Match to query templates if available                    │
│  │                                                                │
│  ├── 5. Context Assembly (L0/L1/L2 tiered loading)              │
│  │      L0 (name+purpose) for all related tables                │
│  │      L1 (columns+relationships) for relevant tables          │
│  │      L2 (full wiki+evidence) for core tables                 │
│  │                                                                │
│  ├── 6. SQL Generation                                           │
│  │      LLM generates SQL with full schema context              │
│  │      Uses enum labels, alias mappings, value patterns         │
│  │                                                                │
│  ├── 7. Validation                                               │
│  │      Parse generated SQL with sqlglot                        │
│  │      Verify all tables/columns exist in knowledge store      │
│  │      Check JOIN conditions match known relationships          │
│  │                                                                │
│  └── 8. Execution (optional, if DB connected)                    │
│         Run query, return results                                │
│         If error → self-correct (rewrite query, retry)           │
│         If success → log as evidence (reinforces knowledge)      │
│                                                                   │
│  Coverage Analysis Engine:                                       │
│  ├── Load domain template (e.g., "retail_customer_lifecycle")    │
│  ├── For each expected touchpoint:                               │
│  │   search schema → report FOUND / PARTIAL / MISSING           │
│  └── Output: coverage report with gap recommendations            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 5: MCP SERVER + SKILLS                   │
│                                                                   │
│  Installation:                                                   │
│  {                                                                │
│    "mcpServers": {                                               │
│      "db-wiki": {                                           │
│        "command": "python",                                      │
│        "args": ["-m", "db_wiki", "serve"],           │
│        "env": { "DB_WIKI_PATH": "./knowledge.sqlite" }     │
│      }                                                           │
│    }                                                             │
│  }                                                               │
│                                                                   │
│  Core Skills (always available):                                 │
│  ├── dbwiki:ingest <path>                                            │
│  │   Parse DDL/SP/trigger files or directories                   │
│  │   Returns: parse count, new entities, new relationships       │
│  │                                                                │
│  ├── dbwiki:ask <question>                                           │
│  │   Natural language → SQL + explanation + optional results     │
│  │   Supports all 6 query tiers                                  │
│  │                                                                │
│  ├── dbwiki:explain <entity>                                         │
│  │   Wiki page for table/column/SP/enum with relationships,     │
│  │   usage patterns, lineage, confidence scores                  │
│  │                                                                │
│  └── dbwiki:search <query>                                           │
│      Hybrid search across wiki + schema + procedures             │
│                                                                   │
│  Discovery Skills (knowledge building):                          │
│  ├── dbwiki:discover [entity]                                        │
│  │   Run investigation loop for specific entity or top-N gaps    │
│  │   Returns: findings + questions for human                     │
│  │                                                                │
│  ├── dbwiki:confirm <entity> <value>=<label>                         │
│  │   Record human-confirmed knowledge (confidence=1.0)           │
│  │                                                                │
│  ├── dbwiki:define_metric <name> = "<definition>"                    │
│  │   Teach the engine a business concept → SQL mapping           │
│  │                                                                │
│  └── dbwiki:lint                                                     │
│      Check contradictions, orphans, stale facts, missing refs    │
│      Returns: health report + recommended actions                │
│                                                                   │
│  Analysis Skills (advanced queries):                             │
│  ├── dbwiki:lineage <table|column>                                   │
│  │   Upstream/downstream data flow through SPs and triggers      │
│  │                                                                │
│  ├── dbwiki:state_machine <table.column>                             │
│  │   Full transition graph with anomaly detection                │
│  │   (backward, skipped, orphan, dead-end states)                │
│  │                                                                │
│  ├── dbwiki:branch_analysis <sp_name>                                │
│  │   Every IF/ELSE/CASE branch with conditions,                  │
│  │   tables touched, and test data requirements                  │
│  │                                                                │
│  ├── dbwiki:forensics <entity_id>=<value> from=<date> to=<date>     │
│  │   Temporal change investigation across all auditable tables   │
│  │   Reports: timeline of changes + audit blind spots            │
│  │                                                                │
│  ├── dbwiki:coverage <domain_template>                               │
│  │   Compare schema against domain reference model               │
│  │   Reports: FOUND / PARTIAL / MISSING per touchpoint           │
│  │                                                                │
│  ├── dbwiki:data_quality [table]                                     │
│  │   Orphan FKs, NULL violations, impossible values,             │
│  │   duplicates, constraint violations                           │
│  │                                                                │
│  └── dbwiki:impact <table|column>                                    │
│      Blast radius: which SPs, triggers, jobs, and downstream     │
│      tables are affected if this entity changes                  │
│                                                                   │
│  Status Skills (observability):                                  │
│  ├── dbwiki:status                                                   │
│  │   Maturity score, gap count, conflict count, coverage %       │
│  │   Breakdown by: tables, columns, enums, relationships,        │
│  │   SP logic, conflicts                                         │
│  │                                                                │
│  └── dbwiki:connect <connection_string>                              │
│      Connect to live database for data sampling + validation     │
│      + query execution                                           │
│                                                                   │
│  Maturity Dashboard (via dbwiki:status):                             │
│  ┌─────────────────────────────────────────────────┐             │
│  │  DATABASE KNOWLEDGE: 67% mature                  │             │
│  │                                                   │             │
│  │  Tables:       ████████████████████░░  189/220    │             │
│  │  Columns:      █████████████░░░░░░░░  2847/4200  │             │
│  │  Enums:        ████████░░░░░░░░░░░░░  89/340     │             │
│  │  Relationships:████████████████░░░░░  312/380    │             │
│  │  SP Logic:     ██████████████░░░░░░░  890/1200   │             │
│  │  State Machines:███████████░░░░░░░░░  18/32      │             │
│  │  Audit Coverage:█████████████████░░░  165/220    │             │
│  │  Conflicts:    14 unresolved                      │             │
│  │  Derived Metrics: 7 defined                       │             │
│  │                                                   │             │
│  │  Top gaps:                                        │             │
│  │  1. dbo.Config — 45 enum columns, 0 labels        │             │
│  │  2. dbo.AuditLog.ActionType — 120 distinct values │             │
│  │  3. sp_LegacyCalc vs sp_NewCalc — score conflict  │             │
│  └─────────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Concern Resolution Matrix

| Concern | Solution Layer | Key Mechanism |
|---------|---------------|---------------|
| C1: Can't learn in one pass | Layer 3: Learning Loop | Five-phase cycle runs hundreds of times, each pass deeper |
| C2: Need loop to upgrade memory | Layer 3: Loop Scheduling | fast/medium/deep/human loops at different frequencies |
| C3: Auto-find gaps | Layer 3: Phase 1 DISCOVER | 12 gap detection rules + priority scoring queue |
| C4: Auto-fix conflicts | Layer 3: Phase 3 REASON | 4-op pipeline (ADD/REINFORCE/CONFLICT/NOOP) + SP reliability scoring |
| C5: Undocumented enums | Layer 2: Value Intelligence + Layer 3: Phase 2 | CASE extraction + SP name hints + data sampling + human confirmation |
| C6: Easy setup (MCP) | Layer 5: MCP Server | Single `pip install`, SQLite file, no Neo4j/Docker |
| C7: NL → exact SQL | Layer 4: Query Engine | 8-step pipeline: concept resolution → path finding → SQL generation → validation |
| C8: Cross-project knowledge | Layer 2: Cross-Project DB | Naming patterns, common enums, schema patterns with confidence penalty |
| M9: SP control flow | Layer 1: SP Parser | IF/ELSE branch extraction, variable tracking, nesting depth |
| M10: State machines | Layer 2: state_transitions + Layer 5: dbwiki:state_machine | UPDATE SET col=X WHERE col=Y extraction + anomaly detection |
| M11: Analytical queries | Layer 4: Query Tiers | 6 tiers: lookup → aggregation → temporal → statistical → forensic → data quality |
| M12: Derived metrics | Layer 2: derived_metrics + Layer 5: dbwiki:define_metric | Human-teachable business concept → SQL mappings |
| M13: Negative knowledge | Layer 4: Coverage Analysis + Layer 5: dbwiki:coverage | Domain templates with expected touchpoints vs actual schema |
| M14: Dynamic SQL + triggers | Layer 1: Trigger/Job Parser + Dynamic SQL detector | Parse triggers same as SPs, flag EXEC(@sql) as opaque, try static resolution |
| M15: Temporal forensics | Layer 2: audit_capabilities + Layer 5: dbwiki:forensics | Auto-discover timestamp/history columns, generate multi-table timeline queries |
| M16: Data quality | Layer 2: data_quality_rules + Layer 5: dbwiki:data_quality | Orphan FK, NULL violations, impossible values, duplicate detection |

---

## 4. Role-Based Challenge Questions

### 4.1 Developer (building new features)

**D1: "I need to add a loyalty points system. Which tables currently track anything related to customer spending, purchase history, or rewards — and how do they connect?"**
- Tests: Multi-concept resolution + relationship path mapping + dead feature detection
- Solved by: dbwiki:ask → concept resolution → BFS graph traversal → wiki assembly

**D2: "I'm refactoring the payment module. Show me every stored procedure that writes to any payment-related table, the exact columns they modify, and which ones share transactions (could cause deadlocks if I change the schema)."**
- Tests: Write-path lineage + transaction scope analysis + SP call chain resolution + dynamic SQL handling
- Solved by: dbwiki:lineage + dbwiki:impact + sp_transaction_scope table

**D3: "What's the difference between `CustomerID`, `CustID`, `Customer_ID`, `CustNo`, and `AccountID`? Are they all the same entity? Which tables use which, and can I safely JOIN across them?"**
- Tests: Alias cluster detection + contextual disambiguation + data type/range validation
- Solved by: column_aliases table + data sampling validation + SP JOIN evidence

### 4.2 Tester (looking for test data and edge cases)

**T1: "I need to test the order cancellation flow. Find me 5 orders in each of these states: partially shipped, fully refunded but still marked active, containing a discontinued product, placed by a customer who no longer exists, and with a negative total amount."**
- Tests: Complex multi-criteria SQL + enum value resolution + data inconsistency detection
- Solved by: dbwiki:ask (Tier 6: Data Quality) + enum_values + dbwiki:data_quality

**T2: "What are all the possible state transitions for an order? I see Status values 0-12 but nobody knows what they mean. Which SPs change the status, and are there any transitions that skip states or go backward?"**
- Tests: Enum discovery + state machine extraction + anomaly detection
- Solved by: dbwiki:state_machine Orders.Status → full transition graph with anomalies

**T3: "Generate a synthetic customer profile that would exercise every code path in `sp_ProcessOrder`. I need to know every branch condition and what data state triggers each branch."**
- Tests: SP branch analysis + cross-table constraint satisfaction + test data generation
- Solved by: dbwiki:branch_analysis sp_ProcessOrder → decision tree + concrete test values

### 4.3 Business Analyst (improving functions, finding insights)

**BA1: "Which customers have been consistently downgrading their orders over the last 6 months? I want to understand the pattern — are they switching to cheaper products, ordering less frequently, or reducing quantities? And what products are they switching FROM and TO?"**
- Tests: Temporal analysis + derived metrics + product hierarchy understanding
- Solved by: dbwiki:define_metric "downgrade" + dbwiki:ask (Tier 3: Temporal)

**BA2: "We suspect some stores are gaming the tournament system to boost their metrics. Find me stores where tournament participation spiked right before quarterly reviews, or where the same players appear across multiple stores' tournaments, or where tournament scores seem statistically abnormal."**
- Tests: Statistical anomaly detection + temporal correlation + cross-entity patterns
- Solved by: dbwiki:ask (Tier 4: Statistical) + multiple investigation queries

**BA3: "Map the complete customer lifecycle from first contact to churn. What touchpoints do we actually track in the database? Where are the gaps — things we should be tracking but aren't?"**
- Tests: Domain concept mapping + schema coverage analysis + gap identification
- Solved by: dbwiki:coverage "retail_customer_lifecycle" → FOUND/PARTIAL/MISSING report

### 4.4 Customer Support / Marketing

**CS1: "A VIP customer is complaining that their tournament ranking dropped after a system update last Tuesday. Show me everything that changed for this customer — scores, rankings, match history, any recalculations — in the 48 hours around that update. Also show me if other customers were affected."**
- Tests: Temporal forensics + multi-table change tracking + impact blast radius
- Solved by: dbwiki:forensics customer_id=X from="2026-04-08" to="2026-04-10" → timeline + blind spots

**CS2: "Marketing wants to run a win-back campaign for churned customers. Define 'churned' for me based on what the data actually shows — what's the typical order frequency by customer segment, when does a gap become unusual, and which churned customers had the highest lifetime value?"**
- Tests: Derived metric definition + segmentation discovery + statistical baselines
- Solved by: dbwiki:define_metric "churn" + dbwiki:ask (Tier 3+4: Temporal + Statistical)

### 4.5 Capability Coverage Matrix

| Capability | D1 | D2 | D3 | T1 | T2 | T3 | BA1 | BA2 | BA3 | CS1 | CS2 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Multi-concept resolution | x | | | | | | x | | | | |
| Write-path / mutation lineage | | x | | | | | | | | | |
| Alias disambiguation | | | x | | | | | | | | |
| Complex multi-criteria SQL | | | | x | | | | | | x | |
| Enum / state machine discovery | | | | | x | | | | | | |
| SP logic deep parsing | | | | | | x | | | | | |
| Temporal / trend analysis | | | | | | | x | x | | x | x |
| Gap / negative knowledge | | | | | | | | | x | | |
| Derived metrics (not stored) | | | | | | | x | | | | x |
| Cross-entity pattern detection | | | | | | | | x | | x | |
| Statistical analysis generation | | | | | | | | x | | | x |
| Impact / blast radius | | x | | | | | | | | x | |
| Data quality / inconsistency | | | | x | | | | | | | |
| Audit infrastructure mapping | | | | | | | | | | x | |

---

## 5. Technology Stack

| Component | Choice | Why (vs alternatives) |
|-----------|--------|----------------------|
| **Storage** | SQLite + sqlite-vec + FTS5 | Zero setup, portable file, hybrid search. No Neo4j needed |
| **Graph traversal** | bfsvtab (from knowledge-graph-rag-mcp) | BFS in SQL, no separate graph DB |
| **SQL parsing** | sqlglot (Python) | Open source, multi-dialect (T-SQL, PL/SQL, MySQL), AST access |
| **Embeddings** | sentence-transformers (local) or OpenAI | Local = free + private, OpenAI = better quality |
| **MCP server** | Anthropic MCP SDK (Python) | Native Claude integration |
| **Learning loop** | Simple Python state machine | No LangGraph overhead, keeps tool lightweight |
| **Bi-temporal** | Custom SQLite schema (Graphiti pattern) | No external dependency |
| **Context tiering** | L0/L1/L2 (OpenViking pattern) | Token-efficient responses |
| **Conflict resolution** | 4-op pipeline (Mem0 pattern) | Proven approach, adapted for domain-specific scoring |
| **Confidence system** | Custom multi-signal scoring (LLM Wiki v2 pattern) | Combines SP evidence, data sampling, human confirmation, recency |

---

## 6. Implementation Phases

### Phase 1 — Skeleton + Ingest (the foundation)
- SQLite schema with bi-temporal model (all tables from Layer 2)
- sqlglot parser: DDL → tables/columns, SP → table refs + JOINs + mutations
- SP control flow analyzer: IF/ELSE branch extraction
- Trigger and SQL Agent job parsing
- Dynamic SQL detection + flagging
- Metadata extraction (sys.columns, execution stats)
- Basic MCP server with `dbwiki:ingest`, `dbwiki:explain`, `dbwiki:search`
- **Usable after this phase:** ingest SPs, ask "what tables exist", "what does this SP touch"

### Phase 2 — Gap Detection + Discovery Loop (the intelligence)
- Gap priority queue with 12 detection rules
- Data sampling engine (live DB connection via `dbwiki:connect`)
- Enum/bitmask auto-detection and labeling
- State machine extraction (transition graphs from UPDATE patterns)
- Audit infrastructure discovery (timestamp columns, history tables)
- Human confirmation skill (`dbwiki:confirm`)
- `dbwiki:discover`, `dbwiki:lint`, `dbwiki:state_machine` skills
- **Usable:** "what don't you know?", "investigate GameMode", "show order status transitions"

### Phase 3 — Conflict Resolution + Self-Correction (the maturity)
- 4-operation update pipeline (Mem0 pattern adapted for DB domain)
- SP reliability scoring
- Contradiction detection + resolution (SUPERSEDE/KEEP/SPLIT/ESCALATE)
- Confidence decay + reinforcement across learning loop iterations
- Alias cluster merging with validation
- **Usable:** "are there any contradictions?", auto-fix wrong facts, reliable knowledge

### Phase 4 — Query Engine (the payoff)
- Concept resolution via hybrid search (vector + FTS5 + wiki)
- Derived metric resolution (`dbwiki:define_metric`)
- JOIN path finding via graph BFS
- 6-tier query generation (lookup → aggregation → temporal → statistical → forensic → data quality)
- Query template library
- SQL validation (parse generated SQL, verify against knowledge store)
- Self-correcting query loop (if error → rewrite → retry)
- `dbwiki:ask`, `dbwiki:forensics`, `dbwiki:data_quality`, `dbwiki:branch_analysis` skills
- **Usable:** "get all tournaments by store in USA" → exact SQL, "what changed for customer X" → timeline

### Phase 5 — Cross-Project + Continuous (the compounding)
- Cross-project pattern database (~/.db-wiki/cross.db)
- Domain templates for coverage analysis (`dbwiki:coverage`)
- Background learning loop scheduling (fast/medium/deep/human)
- Wiki generation (Karpathy compilation pattern, L0/L1/L2 tiers)
- Maturity dashboard (`dbwiki:status`)
- `dbwiki:impact` skill (blast radius analysis)
- **Usable:** full self-sustaining knowledge engine that compounds over time

---

## 7. Integration Layer: Skills, Hooks, Commands, Agents

### 7.1 Design Principles

The tool must be:
- **Clone-and-run**: `git clone` + `pip install` + point at database = working
- **Workflow-agnostic**: fits into Claude Code, IDE extensions, CI/CD, standalone CLI
- **Agent-native**: specialized agents for research, review, and analysis phases ensure quality before knowledge updates
- **Hook-driven**: automated triggers at the right moments without manual invocation

### 7.2 Skills (MCP Tools — invoked by user or LLM)

Skills are the primary interface. Each is a single MCP tool callable by Claude or any MCP client.

```
┌─────────────────────────────────────────────────────────────────┐
│  SKILL CATEGORIES                                                │
│                                                                   │
│  ┌─ LEARN (build knowledge) ─────────────────────────────────┐  │
│  │  dbwiki:ingest <path|glob>                                     │  │
│  │    Parse DDL/SP/trigger files. Batch or incremental.       │  │
│  │    Returns: {parsed: 120, new_tables: 15, new_rels: 43}   │  │
│  │                                                             │  │
│  │  dbwiki:connect <connection_string>                             │  │
│  │    Connect to live DB for sampling + validation + execution│  │
│  │    Stores connection (encrypted) for reuse                 │  │
│  │                                                             │  │
│  │  dbwiki:discover [entity|--top N]                               │  │
│  │    Investigate gaps. Without args: top-10 priority gaps.   │  │
│  │    With entity: deep dive into specific table/column/enum. │  │
│  │    Spawns Research Agent if depth > threshold.             │  │
│  │                                                             │  │
│  │  dbwiki:confirm <table.column> <value>=<label> [value=label...] │  │
│  │    Human confirms enum label, alias, relationship.         │  │
│  │    Sets confidence=1.0, confirmed_by='human'.              │  │
│  │                                                             │  │
│  │  dbwiki:define_metric <name> = "<natural language definition>" │  │
│  │    Teach business concept. Engine maps to SQL automatically│  │
│  │    e.g., dbwiki:define_metric churn = "no order in 2x avg gap" │  │
│  │                                                             │  │
│  │  dbwiki:teach <entity> "<explanation>"                          │  │
│  │    Free-form knowledge injection. For things that can't be │  │
│  │    auto-discovered: business rules, domain context, etc.   │  │
│  │    e.g., dbwiki:teach Orders "Q4 data is unreliable due to     │  │
│  │    migration bug in 2024"                                  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ ASK (query knowledge) ───────────────────────────────────┐  │
│  │  dbwiki:ask <natural language question>                         │  │
│  │    Full query pipeline: concept resolution → path finding  │  │
│  │    → tier classification → SQL generation → validation     │  │
│  │    → optional execution. Supports all 6 query tiers.       │  │
│  │    Returns: {sql, explanation, confidence, data?}          │  │
│  │                                                             │  │
│  │  dbwiki:explain <table|column|sp|enum>                          │  │
│  │    Wiki page with relationships, usage patterns, lineage,  │  │
│  │    confidence scores. Tier-aware (L0/L1/L2).               │  │
│  │    L0 by default, --detail for L1, --full for L2.          │  │
│  │                                                             │  │
│  │  dbwiki:search <query> [--type table|column|sp|enum|fact]       │  │
│  │    Hybrid search: vector + FTS5 + wiki + graph.            │  │
│  │    Returns ranked results with confidence.                 │  │
│  │                                                             │  │
│  │  dbwiki:lineage <table|column> [--direction up|down|both]       │  │
│  │    Data flow: which SPs read/write, upstream/downstream    │  │
│  │    tables, INSERT...SELECT chains, trigger side effects.   │  │
│  │                                                             │  │
│  │  dbwiki:state_machine <table.column>                            │  │
│  │    Full transition graph: from→to, via which SP, conditions│  │
│  │    Anomalies: backward, skipped, orphan, dead-end states.  │  │
│  │                                                             │  │
│  │  dbwiki:branch_analysis <sp_name>                               │  │
│  │    Decision tree: every IF/ELSE/CASE branch with           │  │
│  │    conditions, tables touched, concrete test data needs.   │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ ANALYZE (deep investigation) ────────────────────────────┐  │
│  │  dbwiki:forensics <filter> from=<date> to=<date>               │  │
│  │    Temporal change investigation. Finds all auditable      │  │
│  │    tables for entity, generates timeline query, reports    │  │
│  │    blind spots (tables without timestamps).                │  │
│  │                                                             │  │
│  │  dbwiki:impact <table|column> [--include-data]                  │  │
│  │    Blast radius: SPs, triggers, jobs, downstream tables    │  │
│  │    affected. With --include-data: row count estimates.     │  │
│  │                                                             │  │
│  │  dbwiki:coverage <domain_template>                              │  │
│  │    Schema vs domain reference model.                       │  │
│  │    Reports: FOUND / PARTIAL / MISSING per touchpoint.      │  │
│  │                                                             │  │
│  │  dbwiki:data_quality [table] [--check orphan_fk|nulls|dupes]   │  │
│  │    Data inconsistency scanner. Generates + optionally runs │  │
│  │    diagnostic queries.                                     │  │
│  │                                                             │  │
│  │  db:compare <sp_a> <sp_b>                                   │  │
│  │    Side-by-side logic comparison: what tables, which       │  │
│  │    filters, what calculations, where they disagree.        │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ MANAGE (observability + maintenance) ────────────────────┐  │
│  │  dbwiki:status [--verbose]                                      │  │
│  │    Maturity dashboard: coverage %, gap count, conflicts,   │  │
│  │    top gaps, recent activity, knowledge growth trend.      │  │
│  │                                                             │  │
│  │  dbwiki:lint [--fix]                                            │  │
│  │    Health check: contradictions, orphans, stale facts,     │  │
│  │    broken refs, alias inconsistencies.                     │  │
│  │    With --fix: auto-resolve what it can, escalate rest.    │  │
│  │                                                             │  │
│  │  dbwiki:history <entity>                                        │  │
│  │    Bi-temporal timeline: what we believed, when we learned │  │
│  │    it, what superseded what, confidence over time.         │  │
│  │                                                             │  │
│  │  dbwiki:export [--format md|json|sql|diagram]                   │  │
│  │    Export knowledge: wiki pages, ER diagram, JSON schema,  │  │
│  │    SQL comments (annotate DDL with learned descriptions).  │  │
│  │                                                             │  │
│  │  dbwiki:loop [--depth fast|medium|deep]                         │  │
│  │    Manually trigger learning loop iteration.               │  │
│  │    fast: update confidence, flag gaps                      │  │
│  │    medium: sample data, merge aliases, auto-resolve        │  │
│  │    deep: full scan, bitmask detection, SP validation       │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.3 Hooks (Automated Triggers)

Hooks fire automatically at specific events — no manual invocation needed.

```yaml
# .db-wiki/hooks.yaml (or settings.json for Claude Code)

hooks:
  # ── On Ingest ──────────────────────────────────────────────
  on_file_change:
    description: "When DDL/SP files change on disk"
    trigger: "file watcher detects *.sql modification"
    actions:
      - re-parse changed file
      - diff against previous parse → detect new/removed entities
      - run fast_loop (update confidence, flag new gaps)
      - if new contradictions detected → notify user

  on_ingest_complete:
    description: "After batch ingest finishes"
    trigger: "dbwiki:ingest completes"
    actions:
      - generate ingest summary (new tables, relationships, gaps found)
      - auto-discover top-5 enum columns found in batch
      - update maturity score
      - if maturity dropped (removed entities) → flag for review

  # ── On Query ───────────────────────────────────────────────
  on_query_success:
    description: "When a generated SQL query executes successfully"
    trigger: "dbwiki:ask returns data without error"
    actions:
      - log query as evidence (reinforces concept→table mappings)
      - extract any new column value patterns from results
      - if query used a relationship → reinforce confidence
      - store as query_template for similar future questions

  on_query_failure:
    description: "When a generated SQL query fails"
    trigger: "dbwiki:ask query returns error"
    actions:
      - parse error (missing table? wrong column? type mismatch?)
      - flag affected knowledge as suspect (lower confidence)
      - attempt self-correction (rewrite query)
      - if persistent failure → create gap entry
      - spawn Review Agent to investigate root cause

  on_question_unanswerable:
    description: "When dbwiki:ask can't map concepts to schema"
    trigger: "concept resolution returns no matches above threshold"
    actions:
      - log unmapped concepts as gaps
      - suggest related known concepts to user
      - if live DB connected → attempt exploratory queries
      - store question for future learning (when knowledge improves)

  # ── On Knowledge Update ────────────────────────────────────
  on_conflict_detected:
    description: "When new evidence contradicts existing knowledge"
    trigger: "Phase 3 REASON finds CONFLICT"
    actions:
      - spawn Review Agent to analyze both sides
      - if auto-resolvable (clear winner) → apply + log
      - if ambiguous → queue for human confirmation
      - notify user: "Found conflict: SP-A says X, SP-B says Y"

  on_human_confirmation:
    description: "When user confirms or corrects knowledge"
    trigger: "dbwiki:confirm or dbwiki:teach called"
    actions:
      - set confidence=1.0 on confirmed facts
      - propagate to related facts (if confirming a table
        description, boost confidence of its column descriptions)
      - check if this resolves any queued conflicts
      - update cross-project patterns if applicable
      - run related gap checks (confirming GameMode=5 might
        help resolve GameMode=6)

  # ── On Schedule ────────────────────────────────────────────
  on_session_start:
    description: "When user starts a new Claude session"
    trigger: "MCP server receives first tool call of session"
    actions:
      - inject brief status: "DB Knowledge: 67% mature, 3 new gaps since last session"
      - highlight unresolved conflicts or pending confirmations
      - suggest next action based on priority queue

  on_idle:
    description: "When no user interaction for N minutes"
    trigger: "configurable idle timeout (default: 30 min)"
    actions:
      - run medium_loop iteration in background
      - sample data for top gaps (if DB connected)
      - consolidate episodic → semantic memory
      - update maturity score

  on_schedule:
    description: "Periodic maintenance"
    trigger: "cron-like schedule (configurable)"
    schedules:
      daily:
        - run medium_loop
        - check for schema changes in live DB
        - decay confidence on unconfirmed facts
      weekly:
        - run deep_loop
        - generate knowledge report
        - detect deprecated/dead SPs
        - update cross-project patterns
```

### 7.4 Commands (CLI Interface)

Every skill available as CLI command — for scripting, CI/CD, automation.

```bash
# ── Setup ──────────────────────────────────────────────────
db-wiki init                          # Initialize knowledge store in current dir
db-wiki init --path ./my-knowledge.db # Custom path
db-wiki connect "mssql://user:pass@host/db"  # Connect to live database

# ── Ingest ─────────────────────────────────────────────────
db-wiki ingest ./sql/                 # Ingest all .sql files in directory
db-wiki ingest ./ddl/ --type ddl      # Only parse as DDL
db-wiki ingest ./procs/ --type sp     # Only parse as stored procedures
db-wiki ingest --from-db              # Pull DDL/SP definitions from connected DB
db-wiki ingest --from-db --include triggers,jobs  # Include triggers and jobs
db-wiki ingest --watch ./sql/         # Watch directory for changes (daemon)

# ── Query ──────────────────────────────────────────────────
db-wiki ask "get all tournaments by store in USA"
db-wiki ask "customers who churned last quarter" --execute  # Run against live DB
db-wiki explain Orders                # L0 summary
db-wiki explain Orders --detail       # L1 columns + relationships
db-wiki explain Orders --full         # L2 full wiki page
db-wiki search "payment"              # Hybrid search
db-wiki lineage Orders.CustomerID     # Data flow
db-wiki state-machine Orders.Status   # Transition graph

# ── Discover ───────────────────────────────────────────────
db-wiki discover                      # Top-10 priority gaps
db-wiki discover Games.GameMode       # Deep dive specific column
db-wiki discover --auto               # Non-interactive: auto-resolve what it can
db-wiki confirm Games.GameMode 5="Tournament-Swiss" 7="Practice"
db-wiki define-metric churn "no order in 2x avg order interval"
db-wiki teach Orders "Q4 2024 data is unreliable due to migration bug"

# ── Analyze ────────────────────────────────────────────────
db-wiki forensics --filter customer_id=12345 --from 2026-04-08 --to 2026-04-10
db-wiki impact Orders.Status          # Blast radius
db-wiki coverage retail_customer_lifecycle  # Schema vs domain model
db-wiki data-quality Orders           # Integrity checks
db-wiki compare sp_GetPlayerScore sp_CalcPlayerRating  # SP diff
db-wiki branch-analysis sp_ProcessOrder  # Decision tree

# ── Manage ─────────────────────────────────────────────────
db-wiki status                        # Maturity dashboard
db-wiki status --json                 # Machine-readable
db-wiki lint                          # Health check
db-wiki lint --fix                    # Auto-fix what possible
db-wiki loop --depth medium           # Manual learning loop
db-wiki history Orders.Status         # Bi-temporal timeline
db-wiki export --format md            # Export as markdown wiki
db-wiki export --format diagram       # Export as ER diagram
db-wiki export --format sql-comments  # Annotate DDL with learned descriptions

# ── Daemon ─────────────────────────────────────────────────
db-wiki serve                         # Start MCP server
db-wiki serve --port 8765             # Custom port
db-wiki serve --watch ./sql/          # MCP server + file watcher
db-wiki daemon start                  # Background: file watcher + scheduled loops
db-wiki daemon stop
db-wiki daemon status
```

### 7.5 Agents (Specialized Sub-Processes)

Agents are autonomous workers spawned for tasks that need thorough analysis before making knowledge decisions. They prevent premature or shallow updates.

```
┌─────────────────────────────────────────────────────────────────┐
│                         AGENT SYSTEM                             │
│                                                                   │
│  Each agent:                                                     │
│  - Runs as isolated subprocess with read access to knowledge DB  │
│  - Produces a structured report (not direct DB mutations)        │
│  - Report is reviewed by Orchestrator before applying changes    │
│  - Can be spawned automatically by hooks or manually by user     │
│                                                                   │
│  ┌─ Research Agent ──────────────────────────────────────────┐  │
│  │  Purpose: Deep investigation before knowledge updates      │  │
│  │  Spawned by: dbwiki:discover (when depth > threshold),         │  │
│  │              on_conflict_detected hook,                     │  │
│  │              dbwiki:loop --depth deep                           │  │
│  │                                                             │  │
│  │  What it does:                                              │  │
│  │  1. Receives investigation target (entity + gap type)      │  │
│  │  2. Gathers ALL available evidence:                         │  │
│  │     - Parse every SP referencing the entity                 │  │
│  │     - Sample live data (if DB connected)                    │  │
│  │     - Cross-reference naming patterns                       │  │
│  │     - Check cross-project knowledge                         │  │
│  │     - Analyze column statistics                             │  │
│  │  3. Produces structured report:                              │  │
│  │     {                                                       │  │
│  │       entity: "Games.GameMode",                             │  │
│  │       findings: [                                           │  │
│  │         {value: 5, label: "Tournament-Swiss",               │  │
│  │          confidence: 0.85, evidence: [...]},                │  │
│  │         {value: 7, label: "Practice",                       │  │
│  │          confidence: 0.50, evidence: [...]}                 │  │
│  │       ],                                                    │  │
│  │       conflicts: [...],                                     │  │
│  │       questions_for_human: [                                │  │
│  │         "Is GameMode=12 a beta test? Only 150 rows,        │  │
│  │          appeared Nov 2025, stopped Feb 2026"               │  │
│  │       ],                                                    │  │
│  │       recommended_actions: [...]                            │  │
│  │     }                                                       │  │
│  │  4. Does NOT mutate knowledge DB directly                   │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ Review Agent ────────────────────────────────────────────┐  │
│  │  Purpose: Quality gate before knowledge mutations          │  │
│  │  Spawned by: Phase 3 REASON (before applying changes),     │  │
│  │              on_query_failure hook,                         │  │
│  │              dbwiki:lint --fix                                  │  │
│  │                                                             │  │
│  │  What it does:                                              │  │
│  │  1. Receives proposed knowledge changes                     │  │
│  │  2. Validates each change:                                  │  │
│  │     - Does the evidence actually support this conclusion?  │  │
│  │     - Is the confidence score justified?                    │  │
│  │     - Are there counter-examples we missed?                │  │
│  │     - Would this change break any existing knowledge?      │  │
│  │     - Is there a simpler explanation?                       │  │
│  │  3. Produces verdict:                                       │  │
│  │     {                                                       │  │
│  │       changes_approved: [...],                              │  │
│  │       changes_rejected: [{reason: "insufficient evidence"}]│  │
│  │       changes_modified: [{original: ..., suggested: ...}], │  │
│  │       changes_needs_human: [{reason: "ambiguous"}]         │  │
│  │     }                                                       │  │
│  │  4. Acts as adversarial check — prevents hallucinated      │  │
│  │     knowledge from entering the store                       │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ Analyst Agent ───────────────────────────────────────────┐  │
│  │  Purpose: Complex query decomposition + multi-step analysis│  │
│  │  Spawned by: dbwiki:ask (when query is Tier 3+ complex),       │  │
│  │              dbwiki:forensics, dbwiki:coverage                      │  │
│  │                                                             │  │
│  │  What it does:                                              │  │
│  │  1. Receives complex natural language question              │  │
│  │  2. Decomposes into sub-questions:                          │  │
│  │     "customers downgrading over 6 months" →                │  │
│  │     a. What tables track orders + products?                 │  │
│  │     b. How is product pricing structured?                  │  │
│  │     c. What's the customer→order→product path?             │  │
│  │     d. Is there a pre-built "downgrade" metric?            │  │
│  │     e. What time columns are available?                     │  │
│  │  3. Resolves each sub-question against knowledge store     │  │
│  │  4. Assembles complete query with explanation               │  │
│  │  5. If gaps found during decomposition → creates gap        │  │
│  │     entries (side effect: asking hard questions improves    │  │
│  │     knowledge)                                              │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ Collector Agent ─────────────────────────────────────────┐  │
│  │  Purpose: Systematic data gathering from live database     │  │
│  │  Spawned by: Research Agent (when it needs data samples),  │  │
│  │              dbwiki:discover --auto, deep_loop schedule         │  │
│  │                                                             │  │
│  │  What it does:                                              │  │
│  │  1. Receives sampling tasks from other agents:              │  │
│  │     - SELECT DISTINCT for enum columns                     │  │
│  │     - Value range checks for potential FK columns          │  │
│  │     - Row counts for table sizing                          │  │
│  │     - Timestamp range checks for audit capability          │  │
│  │     - Correlation checks between columns                   │  │
│  │  2. Executes queries with safety limits:                    │  │
│  │     - Read-only (SELECT only, no mutations)                │  │
│  │     - Timeout per query (configurable, default 30s)        │  │
│  │     - Max rows per query (configurable, default 10000)     │  │
│  │     - Total query budget per session                       │  │
│  │  3. Returns structured results to requesting agent          │  │
│  │  4. Caches results to avoid re-querying same data          │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─ Orchestrator ────────────────────────────────────────────┐  │
│  │  Purpose: Coordinates the learning loop and agent lifecycle│  │
│  │  Always running: manages the five-phase loop               │  │
│  │                                                             │  │
│  │  Workflow for knowledge update:                             │  │
│  │                                                             │  │
│  │  1. DISCOVER phase identifies gaps                          │  │
│  │          │                                                  │  │
│  │          ▼                                                  │  │
│  │  2. Spawn Research Agent(s) for top-N gaps                  │  │
│  │     (can run in parallel for independent entities)          │  │
│  │          │                                                  │  │
│  │          ▼ research reports                                 │  │
│  │  3. Spawn Collector Agent if live data needed               │  │
│  │          │                                                  │  │
│  │          ▼ data samples                                     │  │
│  │  4. REASON phase proposes knowledge changes                 │  │
│  │          │                                                  │  │
│  │          ▼ proposed changes                                 │  │
│  │  5. Spawn Review Agent to validate changes                  │  │
│  │          │                                                  │  │
│  │          ▼ approved / rejected / needs-human                │  │
│  │  6. Apply approved changes                                  │  │
│  │     Queue rejected for re-investigation                     │  │
│  │     Present needs-human to user                             │  │
│  │          │                                                  │  │
│  │          ▼                                                  │  │
│  │  7. CONSOLIDATE: update wiki, supersede, generate new gaps  │  │
│  │          │                                                  │  │
│  │          └──→ back to step 1                                │  │
│  │                                                             │  │
│  │  Decision: when to spawn agents vs inline processing:       │  │
│  │  - Simple gap (single enum, one SP) → inline, no agent     │  │
│  │  - Complex gap (multi-table, conflicts) → Research Agent   │  │
│  │  - Any knowledge mutation → Review Agent (always)           │  │
│  │  - Tier 3+ query → Analyst Agent                            │  │
│  │  - Data needed from live DB → Collector Agent               │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.6 Workflow Integration Patterns

The tool fits into any workflow via these integration points:

```
┌─────────────────────────────────────────────────────────────────┐
│  INTEGRATION PATTERN 1: Claude Code (MCP Skills)                │
│                                                                   │
│  # .claude/settings.json                                        │
│  {                                                               │
│    "mcpServers": {                                               │
│      "db-wiki": {                                           │
│        "command": "db-wiki",                                       │
│        "args": ["serve", "--watch", "./sql/"],                   │
│        "env": {                                                  │
│          "DB_WIKI_PATH": "./.db-wiki/knowledge.db",   │
│          "DB_CONNECTION": "mssql://..."                          │
│        }                                                         │
│      }                                                           │
│    }                                                             │
│  }                                                               │
│                                                                   │
│  # .claude/settings.json hooks                                   │
│  {                                                               │
│    "hooks": {                                                    │
│      "PostToolUse": [{                                           │
│        "matcher": "dbwiki:ask",                                      │
│        "command": "db-wiki log-query --from-stdin"                 │
│      }],                                                         │
│      "SessionStart": [{                                          │
│        "command": "db-wiki status --brief"                         │
│      }]                                                          │
│    }                                                             │
│  }                                                               │
│                                                                   │
│  # Claude Code skills (auto-registered)                          │
│  /dbwiki:ask "get tournaments by store in USA"                       │
│  /dbwiki:discover Games.GameMode                                     │
│  /dbwiki:status                                                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  INTEGRATION PATTERN 2: Standalone CLI                           │
│                                                                   │
│  # One-time setup                                                │
│  pip install db-wiki                                 │
│  db-wiki init                                                      │
│  db-wiki connect "mssql://user:pass@host/db"                       │
│  db-wiki ingest --from-db                                          │
│                                                                   │
│  # Daily use                                                     │
│  db-wiki ask "which customers churned last month"                  │
│  db-wiki discover --auto                                           │
│  db-wiki status                                                    │
│                                                                   │
│  # Background daemon                                             │
│  db-wiki daemon start  # file watcher + scheduled loops            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  INTEGRATION PATTERN 3: CI/CD Pipeline                           │
│                                                                   │
│  # On PR with SQL changes                                        │
│  db-wiki ingest ./changed-files.sql                                │
│  db-wiki lint --format github-annotations                          │
│  db-wiki impact <changed-tables> --format markdown >> pr-comment   │
│                                                                   │
│  # Nightly knowledge maintenance                                 │
│  db-wiki loop --depth deep --non-interactive                       │
│  db-wiki export --format md > docs/database-wiki/                  │
│  db-wiki status --json > metrics/knowledge-maturity.json           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  INTEGRATION PATTERN 4: Multi-Agent / Team                       │
│                                                                   │
│  # Shared knowledge store (team database)                        │
│  db-wiki serve --host 0.0.0.0 --port 8765                         │
│                                                                   │
│  # Each team member's Claude connects to same MCP server         │
│  # Knowledge compounds across all team interactions              │
│  # Developer confirms alias → tester benefits immediately        │
│  # BA defines metric → CS can query it right away                │
│                                                                   │
│  # Or: shared knowledge file via git                              │
│  # .db-wiki/knowledge.db committed to repo                  │
│  # Each clone has full knowledge, contributes back               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  INTEGRATION PATTERN 5: IDE Extension                            │
│                                                                   │
│  # VS Code / JetBrains — hover over table name in SQL file       │
│  # → shows L0 summary from wiki                                 │
│  # → click for L1/L2 detail                                     │
│  # → right-click → "Explain relationships"                       │
│  # → right-click → "Show lineage"                                │
│  # → right-click → "Impact analysis"                             │
│                                                                   │
│  # SQL file save hook                                            │
│  # → auto-ingest changed SP                                     │
│  # → show diff in knowledge (new relationships found, etc.)     │
└─────────────────────────────────────────────────────────────────┘
```

### 7.7 Configuration

```yaml
# .db-wiki/config.yaml

# Storage
storage:
  path: "./.db-wiki/knowledge.db"   # main knowledge store
  cross_project: "~/.db-wiki/cross.db"  # shared patterns

# Database connection (for live sampling + execution)
database:
  connection_string: "mssql://user:pass@host/db"  # or env: DB_CONNECTION
  read_only: true                         # safety: never mutate target DB
  query_timeout: 30                       # seconds per query
  max_rows: 10000                         # per result set
  query_budget_per_session: 500           # max queries per learning loop

# Ingest
ingest:
  watch_paths: ["./sql/"]                 # directories to watch
  file_patterns: ["*.sql", "*.ddl"]       # file types to parse
  sql_dialect: "tsql"                     # sqlglot dialect
  include_triggers: true
  include_jobs: true
  detect_dynamic_sql: true

# Learning loop
learning:
  fast_loop: "on_event"                   # runs on every ingest/query
  medium_loop: "daily"                    # or "on_demand"
  deep_loop: "weekly"                     # or "on_demand"
  auto_discover: true                     # proactive gap investigation
  auto_sample: true                       # query live DB for evidence
  max_gaps_per_loop: 20                   # investigate top-N per iteration

# Confidence
confidence:
  initial_sp_evidence: 0.4                # single SP mention
  reinforcement_delta: 0.1                # per additional SP
  human_confirmation: 1.0                 # human says so
  decay_rate: 0.05                        # per month without reinforcement
  min_confidence: 0.1                     # never goes below this
  conflict_threshold: 0.2                 # score gap needed for auto-resolve

# Agents
agents:
  spawn_research_threshold: 3             # spawn agent if gap touches 3+ entities
  spawn_review: "always"                  # always | complex_only | never
  spawn_analyst: "tier3+"                 # tier3+ | tier4+ | never
  max_parallel_agents: 3                  # concurrent agent limit
  collector_safety:
    read_only: true
    timeout: 30
    max_rows: 10000

# Context tiering (token efficiency)
context:
  l0_max_tokens: 50                       # per entity in L0
  l1_max_tokens: 500                      # per entity in L1
  l2_max_tokens: 5000                     # per entity in L2
  default_tier: "l0"
  auto_escalate: true                     # auto-load L1/L2 when needed

# MCP server
server:
  transport: "stdio"                      # stdio | http
  port: 8765                              # for http transport
  auth: null                              # null | token | mtls

# Embeddings
embeddings:
  provider: "local"                       # local | openai
  model: "all-MiniLM-L6-v2"              # for local
  dimensions: 384
  # provider: "openai"
  # model: "text-embedding-3-small"
  # api_key: env:OPENAI_API_KEY

# Export
export:
  auto_wiki: true                         # auto-generate wiki pages on knowledge change
  wiki_path: "./.db-wiki/wiki/"
  diagram_tool: "mermaid"                 # mermaid | plantuml | dbdiagram
```

## 8. Sources

- [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) — SQLite graph + BFS architecture
- [claude-mem](https://github.com/thedotmack/claude-mem) — Progressive disclosure + hooks
- [Mem0](https://github.com/mem0ai/mem0) | [Paper](https://arxiv.org/abs/2504.19413) — 4-op update pipeline + conflict detection
- [Graphiti/Zep](https://github.com/getzep/graphiti) | [Paper](https://arxiv.org/abs/2501.13956) — Bi-temporal model + fact invalidation
- [OpenViking](https://aitoolly.com/ai-news/article/2026-03-16-openviking-an-open-source-context-database-for-ai-agents-designed-for-hierarchical-context-managemen) — L0/L1/L2 tiered context loading
- [Cognee](https://github.com/topoteretes/cognee) — Continuous learning + auto-correction
- [knowledge-graph-rag-mcp](https://pypi.org/project/knowledge-graph-rag-mcp/) — SQLite + sqlite-vec + bfsvtab hybrid
- [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — Wiki compilation + lint pattern
- [LLM Wiki v2](https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2) — Confidence decay + memory tiers
- [Self-Correcting Knowledge Graphs](https://medium.com/globant/self-correcting-knowledge-graphs-with-neo4j-and-llms-35fd36f31ec8) — Inconsistency detection loops
- [LangGraph Self-Correcting RAG](https://learnopencv.com/langgraph-self-correcting-agent-code-generation/) — Self-correcting loop pattern
- [Mem0 State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026) — Memory ecosystem landscape
- [Best AI Agent Memory Frameworks 2026](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/) — Framework comparison
