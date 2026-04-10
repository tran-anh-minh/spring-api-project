# Phase 2: SP Parsing + Knowledge Graph - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the Q&A.

**Date:** 2026-04-10
**Phase:** 02-sp-parsing-knowledge-graph
**Mode:** discuss (interactive)
**Areas discussed:** SP parsing depth, Graph traversal, Embedding + search, Ingest workflow, State transitions, SP call chain resolution, Schema extensions, MCP/CLI tools

## Discussion Summary

### SP Parsing Depth
| Question | Options Presented | Selected |
|----------|------------------|----------|
| How to handle incomplete procedural blocks (IF/ELSE, TRY/CATCH)? | Flatten and extract (rec) / Skip procedural blocks / Two-pass strategy | Flatten and extract |
| How to handle dynamic SQL (EXEC(@sql), sp_executesql)? | Flag and skip (rec) / Attempt string extraction / Flag with context capture | Flag and skip |
| How should degraded SPs surface to users? | Silent metadata (rec) / Warnings during ingest / Summary report after ingest | Silent metadata |
| How aggressive should enum detection be? | CASE + naming heuristics (rec) / CASE only / Broad pattern matching | CASE + naming heuristics |

### Graph Traversal
| Question | Options Presented | Selected |
|----------|------------------|----------|
| bfsvtab vs Python BFS? | Python BFS only (rec) / Try bfsvtab fallback Python / bfsvtab required | Python BFS only |
| Should BFS filter by edge type? | Configurable per query (rec) / Traverse all filter results / Predefined modes | Configurable per query |

### Embedding + Search
| Question | Options Presented | Selected |
|----------|------------------|----------|
| How to handle 384-dim vs 1536-dim mismatch? | Separate tables per provider (rec) / Single table max dim / Config-locked dimension | Separate tables per provider |
| How to combine vector + FTS5 results? | Score fusion (rec) / FTS5 first vector rerank / Vector first FTS5 boost | Score fusion |
| When should embedding happen? | On-demand at first search (rec) / During ingest / Explicit embed command | On-demand at first search |

### Ingest Workflow
| Question | Options Presented | Selected |
|----------|------------------|----------|
| How should SP files be organized? | One SP per file (rec) / Multi-SP files / Both auto-detect | One SP per file |
| What happens when SP file changes (re-parse)? | Invalidate old insert new (rec) / Update in place / Version chain | Invalidate old insert new |
| How should --watch mode work? | Defer to Phase 5 (rec) / Simple polling / OS file watcher | Defer to Phase 5 |
| How should --type flag work? | Auto-detect content (rec) / Required flag / Directory convention | Auto-detect content |

### State Transitions
| Question | Options Presented | Selected |
|----------|------------------|----------|
| How to detect state transitions from UPDATE patterns? | UPDATE WHERE literal match (rec) / Include variable assignments / Broad mutation tracking | UPDATE WHERE literal match |
| What confidence should transitions get? | Evidence-based scoring (rec) / Binary confirmed/unconfirmed / All start at 1.0 | Evidence-based scoring |

### SP Call Chain Resolution
| Question | Options Presented | Selected |
|----------|------------------|----------|
| How to resolve EXEC references? | Name-based matching (rec) / Strict resolution only / Schema-qualified matching | Name-based matching |
| How to handle circular call chains? | Detect and flag (rec) / Prevent at insertion / Ignore cycles | Detect and flag |

### Schema Extensions
| Question | Options Presented | Selected |
|----------|------------------|----------|
| Should intelligence tables be bi-temporal? | All bi-temporal (rec) / Only source tables / Bi-temporal + versioned | All bi-temporal |
| How should vec embeddings relate to entities? | Unified embeddings table (rec) / Per-entity-type tables / Inline on entity tables | Unified embeddings table |

### MCP/CLI Tools
| Question | Options Presented | Selected |
|----------|------------------|----------|
| What MCP tools for Phase 2? | Core query tools (rec) / Full graph exploration / Search only | Core query tools |
| CLI mirror MCP tools? | Mirror MCP tools (rec) / CLI has more commands / CLI ingest-only | Mirror MCP tools |

## Corrections Made

No corrections — all recommended options confirmed.
