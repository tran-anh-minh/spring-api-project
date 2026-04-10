# Pitfalls Research

**Domain:** Database knowledge engine / MCP tool with SQL parsing, knowledge graph, and learning loop
**Researched:** 2026-04-10
**Confidence:** MEDIUM — based on domain analysis and documented behavior of named libraries; external search restricted

---

## Critical Pitfalls

### Pitfall 1: sqlglot Fails Silently on T-SQL Control Flow

**What goes wrong:**
sqlglot parses T-SQL data flow (SELECT, INSERT, JOIN, UPDATE) reasonably well, but T-SQL procedural extensions are not fully supported. Constructs like `BEGIN...END` blocks, `DECLARE @var TABLE (...)`, `INSERT...EXEC`, `EXEC sp_name @param = @var`, `TRY...CATCH`, cursor declarations, `MERGE` statements with complex WHEN clauses, and `GOTO` labels may parse partially or return a degraded AST instead of raising an error. The code gets a result but the AST is incomplete — table refs inside `CATCH` blocks or cursor `FETCH` loops may be silently dropped.

**Why it happens:**
sqlglot's T-SQL dialect support focuses on data manipulation, not procedural language extensions. The library returns partial ASTs when it can't fully resolve syntax rather than raising `ParseError`, so callers assume success. Projects that parse SPs without verifying AST completeness ship with invisible gaps in extraction.

**How to avoid:**
- After parsing each SP, check `ast.find_all(exp.Anonymous)` — anonymous nodes indicate unparsed constructs. Log them as warnings.
- Test against a corpus of at least 20 representative SPs before any other feature. Include SPs with cursors, `INSERT...EXEC`, `MERGE`, and `TRY...CATCH`.
- Build an explicit fallback: if the AST has too many anonymous nodes (>5% of total), flag the SP as "partially parsed" in the knowledge store with `parse_quality = 'degraded'`.
- For dynamic SQL (`EXEC(@sql)`, `sp_executesql`), detect the pattern explicitly at the string level before AST parsing — these will never parse to meaningful data flow.
- Known specific gap: `MERGE ... OUTPUT INTO @table_variable` is structurally complex and likely incomplete in sqlglot's T-SQL dialect.

**Warning signs:**
- Zero table references extracted from SPs you know touch many tables
- Parsed SP body has `exp.Anonymous` nodes wrapping large subtrees
- Control flow extraction returns empty results for a complex SP

**Phase to address:**
Ingest / SP Parser phase. Must be validated before any downstream knowledge graph work.

---

### Pitfall 2: SQLite Graph Queries Become Unbounded at Scale

**What goes wrong:**
Recursive CTEs for BFS traversal in SQLite have no native depth limit enforcement — if you write `WITH RECURSIVE traverse(...)` without a guard, a cyclic relationship graph (which a real database schema will always have via cross-table SPs) causes the query to loop until SQLite hits a recursion depth error or OOM. The bfsvtab approach from codebase-memory-mcp imposes depth limits, but implementing it incorrectly means queries that work on 10-table schemas fail on 500-table schemas.

**Why it happens:**
Developers test graph traversal on small schemas (10-20 nodes) where cycles don't appear. Legacy databases have hundreds of tables with inferred relationships from dozens of SPs each, creating dense graphs. BFS without a visited-node guard iterates the same nodes exponentially.

**How to avoid:**
- Always implement BFS with a `visited` set in the CTE: `WHERE node_id NOT IN (SELECT node_id FROM visited)`.
- Enforce max depth parameter (default 3, max 5) at the query layer, not as a "nice to have."
- Add a row count limit (`LIMIT 10000`) to all recursive queries as a circuit breaker.
- Index `(src_id, dst_id)` on the relationships table — without this, each BFS step does a full table scan.
- Test with a synthetic dense graph (300 nodes, 2000 edges, 15% cycles) before shipping BFS traversal.

**Warning signs:**
- Graph queries take >2s on a 50-table schema
- SQLite raises "too many levels of trigger recursion" or memory errors
- Query results vary unexpectedly on repeated calls (sign of non-deterministic traversal)

**Phase to address:**
Knowledge Store / Graph Storage phase. BFS must be validated at realistic scale before the query engine builds on it.

---

### Pitfall 3: MCP Server Blocks Claude on Long Operations

**What goes wrong:**
MCP servers communicate over stdio. If a Python MCP skill (e.g., `ingest` on 500 SPs) takes 90+ seconds synchronously, Claude Code's MCP client times out and the user sees a connection error. The ingest appears to fail even though it eventually completes in the background. Worse, if the process is killed by timeout, the SQLite database may be left in a partially-written transaction state.

**Why it happens:**
MCP protocol expects request → response within a reasonable window. Python's GIL and synchronous SQLite writes compound the problem: parsing 500 SPs sequentially + embedding generation + graph writes can easily exceed any reasonable timeout. Developers test with 5 SPs and don't discover this until real usage.

**How to avoid:**
- Design all long-running skills to be async from day one: immediately return a `job_id` response, then run the operation as a background task (asyncio task or subprocess).
- Implement `dbwiki:status` / `dbwiki:job_status` skill that Claude can poll to check progress.
- For the `ingest` skill specifically: accept file paths → return immediately → run background ingestion → update progress in SQLite → Claude polls via status skill.
- Ensure all SQLite writes use explicit transactions and `try/except` with rollback so partial failures leave a clean state.
- Use `WAL` journal mode (`PRAGMA journal_mode=WAL`) to allow concurrent reads during long writes.

**Warning signs:**
- MCP connection drops after 30-60 seconds during ingest
- `sqlite3.OperationalError: database is locked` errors
- Knowledge store has incomplete ingest (some SPs missing, no error logged)

**Phase to address:**
MCP Server / Skills layer. Must be designed async-first before any skill implementation. Retrofitting sync skills to async is painful.

---

### Pitfall 4: Learning Loop Produces Confidence Drift Without Decay

**What goes wrong:**
Each learning loop iteration reinforces existing relationships. Without a decay mechanism, old high-confidence facts accumulated from an early (poor-quality) run persist indefinitely even when newer evidence contradicts them. The system converges on stale knowledge: a relationship that was once inferred from 3 SPs and got confidence=0.9 stays at 0.9 even after those SPs are updated or 10 newer SPs contradict the relationship.

**Why it happens:**
The REINFORCE operation naturally only increases confidence. Developers implement ADD/REINFORCE/CONFLICT/NOOP but forget that REINFORCE without a corresponding decay creates monotonically increasing confidence that never reflects source freshness. The Mem0 4-op pattern describes update operations but leaves decay implementation to the consumer.

**How to avoid:**
- Implement time-based confidence decay: `new_confidence = confidence * decay_factor ^ (days_since_last_confirmed / 30)`. Default decay_factor=0.95 means a fact unconfirmed for 6 months decays from 0.9 to ~0.66.
- Store `last_confirmed_at` on every relationship and re-apply decay at the start of each learning loop iteration.
- Implement the CONFLICT operation to actively reduce confidence (not just flag): when two SPs directly contradict a relationship, reduce confidence by 0.2 per conflicting source, floor at 0.1.
- Cap REINFORCE so that confidence never exceeds 1.0 and requires multiple independent sources to reach 0.95+.
- Add a "knowledge age" metric to `dbwiki:status` — relationships older than 90 days without confirmation should appear as "stale."

**Warning signs:**
- High-confidence relationships that don't match current DB schema
- Loop runs produce NOOP for everything (system thinks it knows everything, stops learning)
- User confirms something as wrong but confidence doesn't decrease

**Phase to address:**
Learning Loop / Consolidate phase. Design the decay formula before the REINFORCE operation is implemented.

---

### Pitfall 5: Infinite Loop When Gap Detection Re-queues Its Own Findings

**What goes wrong:**
The gap priority queue is populated by detection rules (unlabeled enums, orphan tables, etc.). If the Investigate phase adds new relationships that trigger new gaps of the same type (e.g., a newly labeled enum column reveals another unlabeled column in the same table cluster), and the queue doesn't deduplicate or bound re-investigation, the loop runs indefinitely. The system investigates gap A → finds gap B → investigates B → finds A again.

**Why it happens:**
Developers implement the detection rules and the investigation phase independently. Detection rules are "pure" functions — given current KB state, output gaps. Investigation updates KB state. Without a "seen gaps" registry or iteration budget, every investigation creates opportunities for re-detection.

**How to avoid:**
- Implement a `gap_history` table with `(gap_type, entity_id, detected_at, resolved_at, resolution_type)`. Before enqueuing a gap, check if it was investigated in the last N days.
- Set a per-entity cooldown: the same gap for the same entity cannot be re-investigated within 24h by default.
- Implement a global iteration budget per learning loop run: `max_investigations = min(50, len(gaps) * 0.1)`. Stop when budget is exhausted, not when the queue is empty.
- Add a convergence check: if the last 3 loop iterations produced <5% new knowledge, switch from "fast" to "deep" frequency and reduce iteration rate.
- Never let the loop self-trigger synchronously — always schedule via the background scheduler with a minimum inter-run gap.

**Warning signs:**
- CPU pegged at 100% during a learning loop run
- SQLite database growing faster than expected (duplicate gap records)
- Loop run time increasing with each iteration instead of decreasing as gaps close

**Phase to address:**
Learning Loop / Discover + Investigate phases. Gap queue design must include deduplication and budget controls from the start.

---

### Pitfall 6: sqlite-vec Degrades Badly on High-Dimensional Embeddings Without Index Tuning

**What goes wrong:**
sqlite-vec provides approximate nearest neighbor (ANN) search via virtual tables. The default configuration does not use HNSW indexing — queries scan all vectors linearly. At 384 dimensions (sentence-transformers default) with 10,000+ vectors (one per table+column+SP combination), a single semantic search takes 200-500ms. At 50,000 vectors (large database), it becomes 2-5 seconds per query, which is unacceptable for interactive use.

**Why it happens:**
sqlite-vec is a newer extension (still maturing in 2025). Developers copy the basic setup from examples, which show small-scale usage. Linear scan is the default; HNSW must be explicitly configured. Additionally, the embedding dimensionality choice (1536 for OpenAI vs 384 for local models) dramatically affects storage and performance, and developers often don't benchmark before shipping.

**How to avoid:**
- Always create the vector index with `CREATE VIRTUAL TABLE vss_entities USING vec0(...)` and verify HNSW support in the sqlite-vec version being used.
- Default to 384-dimensional local embeddings (sentence-transformers `all-MiniLM-L6-v2`) rather than 1536-dimensional OpenAI embeddings — 4x faster, 4x less storage, acceptable quality for code/schema search.
- Implement a hybrid search that uses FTS5 keyword search first (fast, eliminates 90% of candidates) then vector search on the filtered set. This reduces the vector search space from 50,000 to ~500.
- Benchmark semantic search at 1,000 / 10,000 / 50,000 vectors during the Knowledge Store phase, not the Query Engine phase.
- Store embeddings for entities at ingest time, not at query time — embedding generation is the slow step, not retrieval.

**Warning signs:**
- Semantic search takes >500ms on a 1000-entity knowledge store
- Query logs show vector search accounting for >80% of query time
- Memory usage spikes during semantic search (sign of no index, loading all vectors)

**Phase to address:**
Knowledge Store phase (embedding design) + Query Engine phase (hybrid search implementation).

---

### Pitfall 7: Bi-Temporal Schema Complexity Explodes Query Logic

**What goes wrong:**
The bi-temporal model (valid_from/valid_until + recorded_at/invalidated_at) requires every query to add 4 temporal conditions to avoid returning expired, future, or superseded facts. Developers implement the data model correctly but forget to apply temporal filters in BFS traversal, gap detection, and confidence aggregation. The result: the knowledge graph uses outdated relationships (invalidated facts), inflating confidence on stale knowledge.

**Why it happens:**
Temporal queries are non-intuitive. Developers write `SELECT * FROM db_relationships WHERE src_table = 'Orders'` and forget the temporal guards. Even when they add them for the main query, they omit them in subqueries, CTEs, and JOINs. Since the DB has no constraint enforcing temporal correctness, incorrect queries return plausible results silently.

**How to avoid:**
- Create SQLite views for the "current" slice: `CREATE VIEW current_relationships AS SELECT * FROM db_relationships WHERE invalidated_at IS NULL AND valid_until IS NULL OR valid_until > CURRENT_TIMESTAMP`. All application code queries these views — only the ingestion/update pipeline touches raw tables.
- Never query raw temporal tables from the query engine or gap detection layers. Enforce this via code review rule.
- Write a test that inserts a fact, invalidates it, then asserts it does not appear in any view. Run this as part of the CI/CD pipeline.
- Add a bi-temporal query helper function (`get_facts_at(valid_time, recorded_time)`) that encapsulates the 4-condition logic and is used everywhere.

**Warning signs:**
- Knowledge store shows relationships that you know were deleted from SPs
- Confidence levels seem high even after manual correction
- BFS traversal returns paths through tables that no longer exist

**Phase to address:**
Knowledge Store phase. Define the views before any code queries the database.

---

### Pitfall 8: Local Web UI Creates Security Exposure on Shared Machines

**What goes wrong:**
The local web UI for graph visualization, when served on `0.0.0.0` (all interfaces) instead of `127.0.0.1`, becomes accessible to anyone on the same network. On developer machines in corporate environments, this exposes the entire database knowledge graph (including table names, column names, SP logic, enum values) to any machine on the LAN. If the UI serves static files from the working directory, path traversal bugs can expose the SQLite database file itself.

**Why it happens:**
Development web servers default to `0.0.0.0` for convenience (allows testing from phones/tablets). Developers ship the dev config. Static file serving is added quickly without auditing file path construction.

**How to avoid:**
- Hard-code `host='127.0.0.1'` as the default. Require explicit `--host 0.0.0.0` opt-in with a visible warning.
- Serve static files only from a whitelist of known paths (the embedded UI assets directory). Never serve arbitrary paths.
- Add `Content-Security-Policy` headers that block all external resource loading — the graph UI must function with zero external CDN calls (privacy: local-first).
- Implement a random port with `--port 0` as default for CI use, and a stable `--port` option for interactive use.
- Open the browser automatically only when `--open` flag is passed, not by default.

**Warning signs:**
- UI accessible from another machine on the same WiFi
- Browser dev tools show external resource requests (fonts, scripts, CDN)
- Any static file path that is constructed by concatenating user input

**Phase to address:**
Local Web UI phase (final phase). Security defaults must be set before the first working UI commit.

---

### Pitfall 9: Dynamic SQL Is Silently Omitted From the Knowledge Graph

**What goes wrong:**
T-SQL stored procedures frequently build and execute SQL strings: `SET @sql = 'SELECT ... FROM ' + @tableName; EXEC(@sql)` or `EXEC sp_executesql @sql, @params`. These patterns are unparseable by sqlglot at the AST level — the actual table being queried is only known at runtime. If the ingestion pipeline silently skips these, the knowledge graph is missing potentially 20-40% of real data access patterns in heavily dynamic codebases. Users ask "what reads from the Orders table?" and get incomplete answers with no warning.

**Why it happens:**
Developers implement the happy path (static SQL, known tables) first and never revisit dynamic SQL handling. The parser succeeds — it just produces a result with no table references. The knowledge store doesn't distinguish "SP that reads no tables" from "SP we couldn't parse."

**How to avoid:**
- Detect dynamic SQL patterns explicitly with regex on the SP body before AST parsing: `EXEC\s*\(`, `sp_executesql`, `SET\s+@\w+\s*=\s*'SELECT'`. Flag these SPs with `has_dynamic_sql = TRUE`.
- Emit a `dynamic_sql` evidence record linking the SP to affected tables where the table name can be inferred from surrounding context (e.g., `'SELECT * FROM ' + @tableName` — the `@tableName` variable might be resolved from an input parameter or a preceding assignment).
- Include `has_dynamic_sql` count in `dbwiki:status` output so users know the coverage gap.
- Generate a "dynamic SQL inventory" report listing all SPs with dynamic SQL patterns and what context clues are available.
- Never let a SP with dynamic SQL show as `confidence=high` for table coverage — cap its coverage confidence at 0.5.

**Warning signs:**
- SPs in the database touch tables not present in any relationship
- Users report that "ask" skill misses known relationships
- Parsed SP body has zero table references but the SP body contains INSERT/UPDATE/SELECT keywords

**Phase to address:**
Ingest / SP Parser phase. Must be part of the initial parsing design, not a later addition.

---

### Pitfall 10: Confidence Scores Hallucinate Agreement Across Contradictory Sources

**What goes wrong:**
If the REINFORCE operation adds +0.1 confidence for each confirming SP, a relationship confirmed by 10 SPs reaches confidence=1.0 — but if 8 of those SPs are variations of the same "template" procedure and share the same logic, the effective independence of evidence is far lower. The system believes it has strong evidence but really has one source repeated 8 times. Similarly, if two SPs are both wrong (they contradict the actual schema), REINFORCE amplifies the wrong belief.

**Why it happens:**
The 4-op pipeline treats each SP as an independent evidence source. In practice, stored procedure codebases have copy-paste patterns, templated procedures, and shared utility SPs. These are not independent evidence.

**How to avoid:**
- Implement SP body similarity hashing: before counting a SP as a new confirming source, check `jaccard_similarity(new_sp_tokens, existing_evidence_sp_tokens)`. If similarity >0.7, treat it as confirming evidence with weight=0.3 instead of full weight=1.0.
- Weight evidence by SP reliability score (execution frequency, last modified, error rate) — a highly-executed, recently-modified SP counts more than an ancient rarely-run one.
- Use the Collector Agent's data sampling to ground-truth high-confidence relationships: if confidence >0.85, run a live query to verify the JOIN actually exists in real data before locking in the confidence.
- Implement a "minimum independent sources" threshold: no relationship reaches confidence=0.9 without at least 3 dissimilar SPs confirming it.

**Warning signs:**
- Many relationships reach confidence=1.0 quickly (after first learning loop run)
- `dbwiki:status` shows 95% knowledge coverage after processing only 10% of SPs
- User reports confident SQL with wrong JOIN paths

**Phase to address:**
Learning Loop / Consolidate phase. SP similarity comparison must be part of the REINFORCE implementation.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Sync MCP skill handlers | Simpler code initially | Claude connection timeouts on ingest/loop; unrecoverable UX failures | Never — design async from day one |
| Linear sqlite-vec scan (no index) | Zero configuration | 2-5s query time at 50k vectors; kills interactive use | MVP only if corpus <1000 entities |
| Raw temporal table queries (skip views) | Slightly less code | Stale/expired facts appear in results silently; hard to debug | Never — views are free |
| Single confidence increment (+0.1 flat) | Simple implementation | Source independence not weighted; templates inflate confidence | Never — weight by similarity and reliability score from start |
| `0.0.0.0` web UI host | Easy dev testing | LAN exposure of knowledge graph on corporate networks | Never in shipped code |
| Parse SP body as raw text (skip AST) | Faster initial ship | Misses nested table refs, alias resolution, cross-SP lineage | DDL only (tables/columns), not SPs |
| No gap cooldown in priority queue | Simpler queue logic | Infinite loops; CPU thrashing; user can't use tool during loop | Never — minimal cooldown from the start |
| Storing full SP body in knowledge store without hash | Easy retrieval | Can't detect SP body changes; bi-temporal model can't track evolution | Never — always store body hash + modified_at |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| sqlglot T-SQL dialect | Assuming parse success = complete AST | Check for `exp.Anonymous` nodes after every parse; log parse quality score |
| sqlglot T-SQL dialect | Using `transpile()` for analysis (loses structural info) | Use `parse_one()` + AST traversal with `find_all()` — never transpile for knowledge extraction |
| sqlglot T-SQL dialect | Parsing the entire SP body as one statement | Split on `GO` delimiters and `BEGIN...END` blocks first; some constructs only parse in isolation |
| sqlite-vec | Installing without verifying HNSW support | Check version — HNSW support status varies by version; test with `vec_version()` call at startup |
| sqlite-vec | Generating embeddings at query time | Generate at ingest time and store; query-time generation adds 100-500ms per entity |
| MCP stdio transport | Writing debug output to stdout | All debug/logging must go to stderr or a file; stdout contamination breaks the MCP protocol |
| MCP stdio transport | Sending large JSON responses | MCP clients may have message size limits; paginate results for `search` and `history` skills |
| sentence-transformers | Loading model on every request | Load once at server startup, keep in memory; model loading takes 2-5 seconds |
| SQLite WAL mode | Assuming WAL is persistent | `PRAGMA journal_mode=WAL` must be set on every connection open, or stored in `sqlite_master` via pragma |
| Live DB connection (MSSQL) | Using trusted connection on CI/CD | Always fall back gracefully when no live connection available; never block offline usage |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading all SP bodies into memory for analysis | OOM on large codebases | Stream-parse SPs one at a time, store only extracted facts | ~500+ SPs (depends on SP size) |
| Embedding all entities at ingest time synchronously | Ingest takes 10-30 minutes | Batch embed in groups of 64; use background task with progress | >1000 entities |
| BFS without visited-node tracking | Query never returns or returns exponential rows | Always include `NOT IN visited` guard in recursive CTE | Any graph with cycles (~100% of real DB schemas) |
| FTS5 without trigram tokenizer for short identifiers | Poor search for column names like "id", "ts", "amt" | Use `tokenize = "trigram"` for column/table name FTS5 tables | Always — short identifiers are extremely common in DB schemas |
| Writing each extracted fact as individual INSERT | Ingest 10x slower than necessary | Use batch INSERT with `executemany()` or `INSERT ... VALUES (...),(...),(..)` | >10,000 extracted facts |
| Recomputing gap priorities on every loop iteration | Loop startup latency grows with KB size | Incrementally update gap scores using triggers or dirty-flag pattern | >50,000 entities |
| SQLite without WAL mode under concurrent access | Readers block writers; CLI + background loop contend | Set WAL mode; use connection pool with appropriate timeout | Any concurrent CLI + background loop usage |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Web UI served on all interfaces | Full knowledge graph exposed to LAN; corporate compliance violation | Default `127.0.0.1`; `--host` flag with explicit warning |
| Static file serving from working directory | Path traversal → SQLite file download | Serve only from embedded asset directory; validate all paths against whitelist |
| Constructing SQL with string concatenation in data sampling queries | SQL injection via crafted table/column names | Always use parameterized queries; validate table/column names against `sys.objects` before use |
| Storing live DB credentials in knowledge store SQLite | Credentials readable if SQLite file is shared | Store connection strings only in config file with restrictive permissions; never in SQLite |
| MCP skill that accepts arbitrary SQL | Enables write operations if misused | All data-sampling SQL: read-only connection, `SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED`, explicit timeout |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No progress indicator during ingest | User thinks tool is frozen after 30 seconds; Ctrl+C kills partial ingest | Return immediately with job ID; `dbwiki:status` shows ingest progress with entity count |
| Confident answer with no source citation | User trusts wrong SQL; can't verify | Every `ask` response must include: which SPs were the evidence, confidence score, "verify with: `SELECT ...`" |
| Knowledge coverage reported as percentage without denominator | "87% coverage" is meaningless without context | Report as "347/400 tables documented, 89/400 columns labeled, 12 open gaps" |
| Loop runs silently consume resources | User doesn't know why laptop fan is running | All background loop activity logged to `~/.db-wiki/loop.log`; `dbwiki:status` shows last run time and what changed |
| Error messages from sqlglot exposed raw to user | Cryptic internal errors; "unexpected token at position 4832" | Catch all parser errors; return "SP X could not be fully parsed (dynamic SQL detected / unsupported construct)" |
| Graph visualization loads all nodes at once | Browser freezes on 500+ node graph | Default to showing only top-50 most-connected nodes; depth/filter controls; lazy-load on expand |

---

## "Looks Done But Isn't" Checklist

- [ ] **SP Parser:** Parses 20 diverse real-world SPs including ones with cursors, MERGE, TRY...CATCH, INSERT...EXEC — verify table refs are complete, not just from simple SELECT
- [ ] **Dynamic SQL Detection:** `dbwiki:status` shows a "dynamic SQL coverage" count separate from parsed SP count — if zero dynamic SQL SPs in a real codebase, detector is broken
- [ ] **Bi-temporal Views:** Every query in the codebase goes through a view — verify by grepping for direct `FROM db_relationships` without view prefix
- [ ] **Confidence Decay:** Run two ingests 24 hours apart with a fact removed in the second — verify confidence decreases, not stays static
- [ ] **BFS Cycles:** Test graph traversal on a schema with circular FK references (common: `orders.customer_id → customers.id`, `customers.default_order_id → orders.id`) — verify it terminates
- [ ] **MCP Async:** Trigger a 500-SP ingest via MCP and verify Claude receives a response within 2 seconds (job ID); verify ingest completes in background
- [ ] **Web UI Host:** Start UI and attempt to connect from another machine on same network — should fail by default
- [ ] **Embedding Index:** Run semantic search on a 10,000-entity corpus — verify query time <200ms; if not, HNSW index is not active
- [ ] **Gap Deduplication:** Artificially create a looping gap condition (gap A triggers investigation that re-creates gap A) — verify loop terminates within budget

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Incomplete SP parse (silent AST gaps) | MEDIUM | Add `parse_quality` column; re-parse all SPs with new quality check; re-run gap detection |
| Corrupted SQLite from unfinished transaction | LOW-MEDIUM | SQLite's WAL mode auto-recovers on next open; worst case: `sqlite3 db.sqlite ".recover"` |
| Confidence drift (all high, nothing learning) | HIGH | Reset confidence on all inferred (non-declared) relationships to 0.5; re-run full learning loop |
| Infinite gap loop (CPU thrash) | LOW | Kill background process; add cooldown to `gap_history`; re-start with `--loop-budget 20` |
| Web UI LAN exposure discovered | LOW | Change host to `127.0.0.1`; rotate if any sensitive schema data was accessed |
| Wrong bi-temporal state (stale facts in results) | HIGH | Audit `invalidated_at IS NULL` rows; bulk-invalidate facts from a specific ingest run using `recorded_at` window |
| sqlite-vec linear scan (too slow) | MEDIUM | Enable HNSW index; re-insert all vectors into new indexed table; this requires re-ingesting all embeddings |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| sqlglot silent AST gaps | Ingest / SP Parser | Parse 20 real SPs; check `exp.Anonymous` count; assert table refs >0 for known-complex SPs |
| BFS infinite loops on cyclic graphs | Knowledge Store / Graph | Run BFS on synthetic 300-node cyclic graph; assert returns in <1s |
| MCP blocking on long operations | MCP Server layer (design) | Trigger 500-SP ingest via MCP; assert response within 2s; assert ingest completes async |
| Confidence drift without decay | Learning Loop / Consolidate | Run 5 iterations with static KB; assert confidence does not monotonically increase |
| Gap queue infinite loops | Learning Loop / Discover | Inject circular gap; assert loop terminates within budget |
| sqlite-vec performance | Knowledge Store / Query Engine | Benchmark at 1k / 10k / 50k vectors; assert <200ms at 10k |
| Bi-temporal stale facts | Knowledge Store / Schema | Insert + invalidate test; assert invalidated fact absent from all views |
| Web UI LAN exposure | Local Web UI (first commit) | Attempt connection from second machine; assert refused |
| Dynamic SQL omission | Ingest / SP Parser | Ingest SP with `EXEC(@sql)`; assert `has_dynamic_sql=TRUE` in entity record |
| Hallucinated confidence from duplicate sources | Learning Loop / Consolidate | Ingest 10 copy-paste SP variants; assert confidence does not reach 0.9 |

---

## Sources

- sqlglot GitHub issues and documentation (library knowledge, T-SQL dialect known gaps)
- codebase-memory-mcp architecture (SQLite graph at scale — 2.1M nodes, 4.9M edges observed)
- Graphiti/Zep bi-temporal model documentation (fact invalidation patterns)
- Mem0 4-op update pipeline (ADD/REINFORCE/CONFLICT/NOOP design)
- MCP protocol specification (stdio transport requirements, response timing)
- sqlite-vec extension documentation (vector index configuration, HNSW support)
- Domain analysis of T-SQL codebases (dynamic SQL prevalence in legacy systems)
- Confidence: MEDIUM — all claims grounded in library design and architecture analysis; external verification of sqlglot T-SQL gaps and sqlite-vec HNSW specifics was not possible in this session

---
*Pitfalls research for: DB Wiki — database knowledge engine / MCP tool*
*Researched: 2026-04-10*
