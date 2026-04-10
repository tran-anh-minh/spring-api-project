# Feature Research

**Domain:** Database knowledge engine / MCP tool (SQL Server, legacy SP codebases)
**Researched:** 2026-04-10
**Confidence:** MEDIUM — WebSearch/WebFetch unavailable; based on training knowledge of SchemaSpy, dbdocs, DBML, DataGrip, DBeaver, Neo4j Browser, codebase-memory-mcp (DeusData), and claude-mem. All tools well-established; patterns are well-documented in public docs. Flagged as MEDIUM because version-specific claims unverifiable without live fetch.

---

## Feature Landscape

### Table Stakes (Users Expect These)

These features are present in every comparable tool (SchemaSpy, dbdocs, DataGrip, DBeaver). Missing any of them makes db-wiki feel broken rather than just incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Schema ingestion (DDL parsing) | Every db documentation tool parses CREATE TABLE. Baseline expectation. | MEDIUM | sqlglot handles T-SQL DDL; tables, columns, constraints, indexes, types |
| Table + column inventory | SchemaSpy, dbdocs, DBeaver all list schema objects. Users expect a queryable catalog. | LOW | Core entity store: db_tables, db_columns with descriptions |
| FK/relationship detection | SchemaSpy built its reputation on ER diagrams from declared FKs. Declared FKs are non-negotiable. | LOW | Extend to inferred FKs via JOIN analysis — that's differentiating |
| Natural language query | This is the Core Value. Without it, the tool is just a schema dumper. | HIGH | 6-tier query generation; self-correcting loop |
| SQL output for queries | Users need runnable SQL, not just descriptions. DataGrip/DBeaver generate SQL snippets. | MEDIUM | Validate generated SQL with sqlglot before returning |
| MCP protocol compliance | Target users are Claude Code users. If it doesn't work as an MCP tool, it has no delivery vehicle. | MEDIUM | Anthropic MCP spec; all skills exposed as tools |
| CLI interface | Power users and CI/CD pipelines require a CLI. codebase-memory-mcp has CLI + MCP dual mode. | LOW | CLI mirrors MCP skills; same underlying engine |
| Zero-infrastructure setup | "npm/pip install, point at DB" is the modern expectation for MCP tools. Any Docker/Neo4j requirement kills adoption. | LOW | SQLite only; single-file knowledge store |
| Offline-capable operation | Users want analysis from DDL files without a live DB connection. SchemaSpy works from JDBC; dbdocs from DBML files. | MEDIUM | Two modes: file-only (DDL) and enhanced (file + live DB) |
| Search / entity lookup | Every tool has search. Users type a table or SP name to find it. | LOW | Hybrid search: FTS5 keyword + sqlite-vec semantic |
| Ingest progress feedback | Long ingestion (thousands of SPs) must show progress. Otherwise users think it's hung. | LOW | Progress events via MCP tool streaming or CLI output |
| Status / coverage dashboard | "How much does this tool actually know?" — SchemaSpy has coverage stats, dbdocs has completeness indicators. | MEDIUM | dbwiki:status skill; coverage %, gap count, conflict count |

### Differentiators (Competitive Advantage)

No existing tool does these. They are the reason db-wiki exists.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Stored procedure AST parsing | SchemaSpy only reads DDL. dbdocs only reads DBML. Nobody parses SP bodies to extract JOINs, mutations, and control flow. This is the primary knowledge source for legacy databases where SP logic IS the schema. | HIGH | sqlglot AST; extract table refs, JOIN paths, INSERT/UPDATE/DELETE targets, IF/ELSE branches |
| Self-learning loop with gap detection | No tool proactively identifies what it doesn't know and schedules investigation. This converts a one-shot importer into a living knowledge engine. | HIGH | Gap priority queue with 12 detection rules; 4-agent architecture |
| Enum / bitmask auto-labeling | Legacy DBs use integer codes everywhere. Nobody automatically discovers that Status=4 means "Suspended" by cross-referencing CASE statements, SP names, and sampled data. | HIGH | Evidence fusion: CASE analysis + SP name inference + data sampling + human confirmation |
| State machine extraction | SP codebases encode workflow logic as `UPDATE SET Status=X WHERE Status=Y`. No tool visualizes these as transition graphs. Critical for understanding order processing, billing workflows, etc. | HIGH | Pattern matching across all SPs; emit as graph edges + wiki page |
| SP reliability scoring | When SP-A says orders.status=1 means "active" and SP-B says it means "pending", users need to know which SP to trust. Nobody does this. | MEDIUM | Evidence: execution frequency, last_modified, caller count, contradiction rate |
| Confidence decay and reinforcement | Knowledge freshness degrades over time. A fact confirmed 18 months ago needs re-validation. Pioneered by LLM Wiki v2; no commercial DB tool does this. | MEDIUM | Decay function; gap detection triggers re-investigation |
| Bi-temporal knowledge model | Tracks both "when was this fact true in the DB" and "when did we learn it." Critical for tracking SP evolution. Borrowed from Graphiti/Zep; novel in DB documentation space. | HIGH | valid_from/until + recorded_at/invalidated_at on every fact |
| Data sampling engine | Live DB queries (SELECT DISTINCT, value ranges, row counts) to validate hypotheses about enum values and FK relationships. SchemaSpy reads metadata; nobody validates values. | MEDIUM | Collector Agent; configurable timeout + max rows + query budget |
| Derived metric / business concept mapping | "Churn", "lifetime value", "active player" are not columns. A teachable layer maps business concepts to SQL. Nobody in the DB documentation space does this. | MEDIUM | dbwiki:define_metric + dbwiki:teach skills; persisted metric store |
| Cross-project pattern database | Knowledge from analyzing DB-A (e.g., `is_deleted` pattern, `Status` enum values) informs analysis of DB-B. No tool shares learning across projects. | MEDIUM | ~/.db-wiki/cross.db; naming patterns, common enums, schema patterns |
| SP call chain visualization | SP-A calls SP-B calls SP-C — the impact chain. DBeaver shows direct FK dependencies; nobody traces SP execution chains. | MEDIUM | Call chain extraction during SP parse; lineage skill |
| Control flow branch analysis | IF/ELSE branches in SPs encode business rules. Extracting them exposes hidden logic. No documentation tool does this. | HIGH | Variable tracking, nesting depth, branch condition analysis |
| Dynamic SQL detection and flagging | `EXEC(@sql)` makes static analysis impossible. Flagging these as opaque zones with a confidence penalty is the honest approach. No tool does this. | LOW | Pattern detection during AST parse; flag node type = DYNAMIC |
| Contradiction detection and resolution | Two SPs contradict. Auto-detect via embedding similarity; resolve via SUPERSEDE/KEEP/SPLIT/ESCALATE. Nobody does automated DB knowledge conflict resolution. | HIGH | 4-op pipeline adapted from Mem0 |
| Wiki page generation per entity | Compile everything known about a table into a structured wiki page with evidence citations. Inspired by Karpathy LLM Wiki; novel in DB documentation space. | MEDIUM | L0/L1/L2 tiered generation; dbwiki:explain skill |
| Temporal forensics | "What changed for customer X in the last 48 hours?" requires knowing which tables have audit timestamps, history tables, change tracking. No DB documentation tool answers this. | MEDIUM | Audit infrastructure discovery; temporal query tier |
| Data quality query generation | Generate queries to find broken FK references, impossible values, orphan records. A specialized query type that DB admins need but must hand-write today. | MEDIUM | data_quality tier in query generator; dbwiki:data_quality skill |
| Local graph visualization UI | Interactive web page to explore the knowledge graph visually (tables, relationships, SP connections). Inspired by codebase-memory-mcp and Neo4j Browser. Local-first, no server. | MEDIUM | See Graph UI section below |
| Human confirmation workflow | `dbwiki:confirm` lets a human set confidence=1.0 on a fact, overriding all automated inference. Closes the last-mile gap that no automated tool can bridge. | LOW | Single skill; updates confidence + triggers reinforcement propagation |

### Graph Visualization UI — Feature Breakdown

This deserves its own subsection. The user explicitly wants a local web page inspired by codebase-memory-mcp.

**Table stakes for a graph web UI (what Neo4j Browser, Gephi, and codebase-memory-mcp all do):**

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Node + edge rendering | The fundamental output of any graph UI. | LOW | vis.js, D3 force-directed, or Cytoscape.js — all work offline |
| Node type color coding | Tables vs SPs vs enums vs triggers need visual differentiation. Neo4j Browser colors by label. | LOW | CSS class per node type |
| Click-to-expand neighbors | Click a node → show its direct connections. Standard in Neo4j Browser and codebase-memory-mcp. | LOW | BFS depth=1 on click; render new nodes |
| Search / filter by name | Type a table name, highlight / center on it. Every graph UI has this. | LOW | FTS over rendered nodes |
| Zoom + pan | Essential for large graphs. D3/vis.js provide this out of box. | LOW | Built into force-directed libraries |
| Edge type labels | "reads_from" vs "writes_to" vs "fk_declared" must be distinguishable. | LOW | Edge label rendering; optional toggle to show/hide |
| Detail panel on node click | Click a table → see description, column count, confidence score, wiki excerpt. codebase-memory-mcp does this. | LOW | Side panel populated via API call |

**Differentiating graph UI features (what makes db-wiki's UI better):**

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Confidence heat-mapping | Color node/edge opacity by confidence score. Instantly shows what the engine knows well vs guesses. No other DB graph UI does this. | LOW | Map confidence [0,1] to color intensity |
| SP overlay mode | Toggle: show only tables (clean ER view) or include SPs and triggers as nodes. Users switch contexts fluidly. | LOW | Node type filter toggle; re-render |
| State machine view | For a selected table, show its Status column transition graph (States as nodes, UPDATE patterns as edges). No other tool renders this. | MEDIUM | Separate layout mode; query state_machine endpoint |
| Gap highlighting | Nodes with gaps (unlabeled enums, missing descriptions, stale facts) rendered with visual indicator (dashed border, warning icon). | LOW | Query gap queue; apply CSS class |
| Lineage flow view | Select an SP → show what it reads and writes as a left-to-right data flow diagram (not force-directed). Better for understanding ETL-like SPs. | MEDIUM | Dagre layout for selected SP subgraph |
| Live refresh | When the learning loop runs and updates the graph, the UI refreshes without full page reload. | LOW | Polling or SSE from local server |
| Depth slider | Control BFS depth (1-5 hops) for neighborhood expansion. codebase-memory-mcp does this; it's proven useful. | LOW | Slider → API call with depth param |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Real-time CDC / streaming ingestion | "Keep the knowledge graph always up to date" sounds valuable | Requires Kafka/Debezium infrastructure that violates zero-infrastructure constraint (C6). Complexity explodes. Value is marginal for legacy DBs that change slowly. | Scheduled batch re-ingestion on user-configured frequency. Hook on file change covers DDL updates. |
| Write operations to target database | "Fix the data quality issues you find" seems like a natural next step | Transforms a read-only analysis tool into a DBA automation tool — completely different risk profile, liability surface, and testing burden. One wrong write destroys trust permanently. | Generate the corrective SQL, let the user execute it after review. |
| Multi-dialect support (v1) | "Support PostgreSQL too" immediately | Forces abstraction layer over sqlglot's dialect-specific features. T-SQL control flow (EXEC, @@variables, temp tables) needs special handling. Going wide before going deep produces a mediocre tool for every dialect. | Ship T-SQL v1, prove the pattern, then add dialects with proper testing. |
| GUI desktop application (Electron) | "Make it a full app with menus" | Electron adds 100MB+ binary overhead, OS-specific packaging, update management — all for features the MCP + web UI already provide. Marginal UX improvement for massive maintenance burden. | MCP + CLI + local web UI serves all use cases without desktop app overhead. |
| Authentication / multi-user server | "We want to share this across the team" | Network-accessible multi-user mode requires auth, session management, permission models, and audit logging — a completely different product. | Local-first single-user tool. Teams share by pointing at same SQLite file on shared drive (read-only for non-owner). |
| LLM-dependent extraction (v1) | "Use an LLM to understand SP bodies" | LLM extraction is expensive (thousands of SPs × LLM calls = hundreds of dollars), slow, and non-deterministic. sqlglot AST is deterministic, free, and fast. | sqlglot AST for structural extraction; LLM only for synthesis (wiki generation, conflict resolution, gap prioritization). |
| Built-in ER diagram export (PDF/PNG) | SchemaSpy and dbdocs both do this, so "we should too" | High implementation cost (headless browser or PDF lib), limited value vs the interactive graph UI. Static diagrams go stale; the live web UI doesn't. | Point users at the interactive web UI, or export graph data as DOT/JSON for Graphviz. |
| Chatbot UI / conversation interface | "Build a chat window in the web UI" | The MCP protocol IS the chat interface — Claude Code is the chat window. Building a second chat UI duplicates Claude's entire natural language layer. | Keep web UI as graph visualization only. All NL interaction goes through Claude Code via MCP. |
| Plugin/extension system (v1) | "Make it extensible" | Plugin systems require stable APIs, versioning, documentation, and community management — before the core API is even validated. Premature extensibility creates bad abstractions. | Ship a clean Python API internally; open-source the codebase. External devs fork and PR. Plugin system if/when community demands it. |
| Vector database migration (Pinecone, Weaviate) | "sqlite-vec won't scale" | Introduces infrastructure dependency (violates C6). sqlite-vec handles millions of vectors adequately for single-database analysis. The entire value prop is zero-infra. | Stay with sqlite-vec. If a user has a DB so large that sqlite-vec struggles, that's a v2 problem. |

---

## Feature Dependencies

```
[DDL Parser]
    └──requires──> [Knowledge Store Schema]
                       └──enables──> [Schema Search]
                       └──enables──> [Natural Language Query]
                       └──enables──> [Wiki Generation]
                       └──enables──> [Graph Visualization UI]

[SP Parser (sqlglot AST)]
    └──requires──> [DDL Parser] (table names must resolve)
    └──enables──> [Relationship Graph] (JOIN edges)
    └──enables──> [SP Call Chains]
    └──enables──> [State Machine Extraction]
    └──enables──> [Control Flow Analysis]
    └──enables──> [SP Reliability Scoring]

[Relationship Graph]
    └──requires──> [DDL Parser]
    └──requires──> [SP Parser] (for inferred FKs)
    └──enables──> [JOIN Path Finding (BFS)]
    └──enables──> [Lineage View]
    └──enables──> [Impact Analysis]

[Gap Detection]
    └──requires──> [Knowledge Store] (needs entities to gap-check)
    └──requires──> [Relationship Graph]
    └──enables──> [Learning Loop scheduling]
    └──enables──> [Data Sampling Engine] (gaps trigger samples)

[Data Sampling Engine]
    └──requires──> [Live DB Connection] (optional but needed for sampling)
    └──requires──> [Gap Detection] (knows what to sample)
    └──enables──> [Enum Auto-labeling]
    └──enables──> [FK Validation]

[Enum Auto-labeling]
    └──requires──> [SP Parser] (CASE statements)
    └──requires──> [Data Sampling Engine] (value distribution)
    └──enables──> [State Machine Extraction] (needs labeled states)
    └──enables──> [Data Quality Queries]

[Confidence Scoring]
    └──requires──> [Knowledge Store]
    └──requires──> [SP Reliability Scoring]
    └──enables──> [Confidence Decay]
    └──enables──> [Contradiction Detection]
    └──enables──> [Confidence Heat-map in UI]

[Contradiction Detection]
    └──requires──> [Confidence Scoring]
    └──requires──> [SP Reliability Scoring]
    └──enables──> [4-op Update Pipeline]

[Wiki Generation]
    └──requires──> [Knowledge Store with descriptions]
    └──requires──> [Relationship Graph]
    └──requires──> [Confidence Scoring]
    └──enhances──> [Natural Language Query] (richer context)

[Graph Visualization UI]
    └──requires──> [Knowledge Store] (node/edge data)
    └──requires──> [Local HTTP server] (serves static files + API)
    └──enhances──> [Gap Detection] (visual gap indicators)
    └──enhances──> [State Machine Extraction] (visual state view)

[Human Confirmation]
    └──requires──> [Confidence Scoring]
    └──enhances──> [Gap Detection] (closes confirmed gaps)
    └──conflicts──> [Fully Automated Mode] (needs human present)

[Derived Metric Store]
    └──requires──> [Natural Language Query] (metrics are expressed as NL→SQL)
    └──requires──> [Knowledge Store] (validates column references)
    └──enables──> [Business Concept Queries]

[Cross-project Pattern DB]
    └──requires──> [Enum Auto-labeling] (patterns to share)
    └──requires──> [Knowledge Store] (source of patterns)
    └──enhances──> [Gap Detection] (cross-project hints)
```

### Dependency Notes

- **SP Parser requires DDL Parser:** SP bodies reference table and column names. Without the DDL inventory, SP-extracted relationships cannot be validated and will have lower confidence.
- **State Machine Extraction requires Enum Auto-labeling:** A state machine is meaningless if Status=1,2,3 aren't labeled. Label first, then extract transitions.
- **Data Sampling Engine requires Gap Detection:** Sampling is expensive (DB queries). It should only run when gap detection has identified specific hypotheses worth testing, not blindly on all columns.
- **Graph Visualization UI requires Local HTTP server:** The web page needs an API endpoint to query the knowledge store. A minimal FastAPI/Flask server (or Python's built-in http.server) serves both the static page and a `/api/graph` endpoint.
- **Human Confirmation conflicts with Fully Automated Mode:** The learning loop can run headlessly, but human confirmation requires interaction. These are separate operating modes, not incompatible features — the loop just queues confirmation requests and waits.

---

## MVP Definition

### Launch With (v1)

Minimum viable to validate the Core Value: "Turn undocumented legacy databases into queryable, self-improving knowledge."

- [ ] DDL parsing → tables, columns, constraints, indexes in SQLite — foundational; everything else builds on it
- [ ] SP parsing via sqlglot AST → JOIN extraction, table reads/writes → most of the knowledge comes from here
- [ ] Relationship graph with declared FK + inferred FK from JOINs — required for JOIN path finding
- [ ] JOIN path finding (BFS) — required for SQL generation
- [ ] Natural language → SQL (at least lookup + aggregation tiers) — the Core Value delivery mechanism
- [ ] SQL validation with sqlglot — prevents returning broken SQL
- [ ] Hybrid search (FTS5 + sqlite-vec) — required for concept resolution in queries
- [ ] dbwiki:ask, dbwiki:explain, dbwiki:search, dbwiki:ingest, dbwiki:status skills — minimum MCP surface
- [ ] CLI mirroring the above skills — required for CI/CD and non-Claude usage
- [ ] Gap detection (at least: unlabeled enum columns, missing descriptions, orphan tables) — enables v1 learning loop
- [ ] Enum auto-labeling from CASE statements + SP name inference — unblocks the highest-value gap type
- [ ] Human confirmation (dbwiki:confirm) — closes gaps that automation cannot
- [ ] Confidence scoring on relationships — prevents over-trusting weak inferences
- [ ] Wiki page generation (L0/L1/L2) — the explain skill output format
- [ ] Graph visualization web UI (basic: nodes, edges, color by type, click for detail) — validates the visual exploration concept

### Add After Validation (v1.x)

Add when v1 validates that users find the core workflow valuable.

- [ ] Data sampling engine — trigger: users ask "why is this enum wrong?" (live DB validation needed)
- [ ] State machine extraction — trigger: users ask about workflow/status transitions
- [ ] SP call chain resolution and visualization — trigger: users ask "what does SP-X affect?"
- [ ] SP reliability scoring — trigger: contradictions accumulate and users notice confidence issues
- [ ] Contradiction detection + 4-op resolution pipeline — trigger: same as above
- [ ] Confidence decay + reinforcement — trigger: knowledge goes stale and users notice
- [ ] Temporal forensics (audit infrastructure discovery + temporal query tier) — trigger: forensic use cases emerge
- [ ] Data quality query tier — trigger: testers/QA users appear
- [ ] Derived metric store (dbwiki:define_metric, dbwiki:teach) — trigger: BA users ask business concept questions
- [ ] Graph UI enhancements: confidence heat-map, state machine view, lineage flow view, gap highlighting
- [ ] Control flow branch analysis (IF/ELSE extraction) — trigger: developers ask "what business rules does SP-X encode?"

### Future Consideration (v2+)

Defer until product-market fit is established.

- [ ] Cross-project pattern database — requires multiple users across multiple projects; validate single-project first
- [ ] Dynamic SQL detection refinement — v1 flags EXEC(@sql) as opaque; v2 could attempt partial analysis
- [ ] Additional query tiers: statistical (window functions), forensic (temporal forensics) — defer until user demand
- [ ] Multi-dialect support (PostgreSQL, MySQL) — defer until T-SQL approach is proven
- [ ] CI/CD integration hooks (on_file_change automation) — v1 is manual ingestion; automate after workflow is understood
- [ ] Advanced graph UI: subgraph export, layout algorithms (Dagre for lineage, force-directed for exploration), live refresh via SSE

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| DDL parsing → entity store | HIGH | LOW | P1 |
| SP AST parsing (JOINs, reads/writes) | HIGH | HIGH | P1 |
| Natural language → SQL | HIGH | HIGH | P1 |
| SQL validation (sqlglot) | HIGH | LOW | P1 |
| Hybrid search (FTS5 + vectors) | HIGH | MEDIUM | P1 |
| MCP skill surface (ask, explain, ingest) | HIGH | MEDIUM | P1 |
| CLI interface | MEDIUM | LOW | P1 |
| Graph visualization UI (basic) | MEDIUM | MEDIUM | P1 |
| Gap detection | HIGH | MEDIUM | P1 |
| Enum auto-labeling (CASE + SP names) | HIGH | MEDIUM | P1 |
| Human confirmation skill | MEDIUM | LOW | P1 |
| Wiki page generation | MEDIUM | MEDIUM | P1 |
| Confidence scoring | HIGH | MEDIUM | P1 |
| Data sampling engine | HIGH | MEDIUM | P2 |
| State machine extraction | HIGH | HIGH | P2 |
| SP call chain resolution | HIGH | MEDIUM | P2 |
| SP reliability scoring | MEDIUM | MEDIUM | P2 |
| Contradiction detection + 4-op pipeline | HIGH | HIGH | P2 |
| Confidence decay + reinforcement | MEDIUM | MEDIUM | P2 |
| Temporal forensics | MEDIUM | MEDIUM | P2 |
| Data quality queries | MEDIUM | MEDIUM | P2 |
| Derived metric store | MEDIUM | MEDIUM | P2 |
| Graph UI: confidence heat-map | MEDIUM | LOW | P2 |
| Graph UI: state machine view | MEDIUM | MEDIUM | P2 |
| Graph UI: gap highlighting | MEDIUM | LOW | P2 |
| Control flow branch analysis | MEDIUM | HIGH | P2 |
| Cross-project pattern database | LOW | MEDIUM | P3 |
| Advanced graph layouts (Dagre, SSE refresh) | LOW | MEDIUM | P3 |
| Multi-dialect support | LOW | HIGH | P3 |
| CI/CD automation hooks | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible (post-validation)
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

| Feature | SchemaSpy | dbdocs / DBML | DataGrip / DBeaver | codebase-memory-mcp | db-wiki |
|---------|-----------|---------------|-------------------|---------------------|---------|
| DDL parsing | Yes (JDBC) | Yes (DBML format) | Yes (JDBC) | No (code, not SQL) | Yes (sqlglot, file-based) |
| FK / relationship detection | Declared FKs only | Declared FKs only | Declared + some inferred | N/A | Declared + inferred from SP JOINs |
| SP / stored procedure analysis | No | No | Syntax highlight only | N/A | Full AST: JOINs, mutations, branches, call chains |
| Search / entity lookup | Static HTML search | Web UI search | IDE search | Keyword + semantic | FTS5 + sqlite-vec hybrid |
| Natural language → SQL | No | No | AI Assistant (cloud, paid) | No | Yes, 6-tier query generation |
| Enum / value labeling | No | Manual annotation | No | No | Auto from CASE + sampling + human confirm |
| State machine visualization | No | No | No | No | Yes, from UPDATE transition patterns |
| Knowledge confidence scoring | No | No | No | No | Yes, multi-source evidence model |
| Contradiction detection | No | No | No | No | Yes, 4-op pipeline |
| Self-learning loop | No | No | No | No | Yes, 4-agent iterative loop |
| Graph visualization | Static PNG/SVG | Static web page | ERD diagram | Interactive web UI | Interactive web UI (inspired by codebase-memory-mcp) |
| Live DB data sampling | No | No | Yes (query console) | No | Yes, Collector Agent with safety limits |
| MCP integration | No | No | No | Yes | Yes, primary delivery mechanism |
| Zero infrastructure | Requires JVM | Cloud-hosted | JVM / desktop app | Yes (SQLite) | Yes (SQLite only) |
| CLI interface | Yes | Yes (dbml-cli) | No | Yes | Yes |
| Offline / file-only mode | Yes | Yes | No | Yes | Yes |
| Business concept mapping | No | No | No | No | Yes (derived metric store) |
| Cross-project patterns | No | No | No | No | Yes (cross.db) |

---

## Sources

**Confidence notes for competitor analysis:**
- SchemaSpy: MEDIUM confidence. Well-documented open-source tool; feature list stable over years. schemaspy.org and GitHub README are primary sources.
- dbdocs / DBML: MEDIUM confidence. dbdocs.io and dbml.dbdiagram.io well-documented; cloud-hosted model well established.
- DataGrip / DBeaver: MEDIUM confidence. JetBrains and DBeaver docs are comprehensive; AI Assistant feature confirmed in DataGrip 2024 release notes from training data.
- codebase-memory-mcp: HIGH confidence. Project directly analyzed in existing research (`db-wiki-research.md`); user has first-hand experience.
- Neo4j Browser graph UI patterns: MEDIUM confidence. Neo4j Browser feature set is well-documented; click-to-expand, color by label, detail panel are canonical features.
- vis.js / D3 / Cytoscape.js: MEDIUM confidence. All active, widely-used graph rendering libraries; offline-capable, no CDN required.

**Tools analyzed:**
- SchemaSpy (open source, Java, JDBC-based schema documentation)
- dbdocs.io + DBML (database markup language, cloud-hosted docs)
- DataGrip (JetBrains commercial IDE)
- DBeaver (open-source DB GUI)
- codebase-memory-mcp / DeusData (SQLite graph + MCP, analyzed in existing research)
- claude-mem / thedotmack (progressive disclosure memory, analyzed in existing research)
- Mem0 (4-op update pipeline, analyzed in existing research)
- Neo4j Browser (graph visualization reference)
- Graphiti / Zep (bi-temporal graph, analyzed in existing research)

---

*Feature research for: database knowledge engine / MCP tool (db-wiki)*
*Researched: 2026-04-10*
