# DB Wiki — Setup Tutorial

A step-by-step guide to setting up DB Wiki for a new database project.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager (recommended)
- SQL Server ODBC Driver 17 or 18 (only if connecting to a live database)

## Step 1: Install DB Wiki

```bash
# Option A: Install from source (development)
git clone https://github.com/tran-anh-minh/spring-api-project.git
cd spring-api-project
git checkout db-wiki
uv sync

# Option B: Install with uv (when published)
uv add db-wiki

# Option C: Install with pip
pip install db-wiki
```

Verify the installation:

```bash
db-wiki --help
```

You should see a list of available commands.

## Step 2: Initialize a Knowledge Store

Navigate to your project directory and create a new knowledge store:

```bash
cd /path/to/your/project
db-wiki init
```

This creates a `.db-wiki/` directory containing:

- `config.yaml` — configuration file
- `knowledge.db` — SQLite knowledge store (single file, zero infrastructure)

You can specify a custom path:

```bash
db-wiki init --store-path /path/to/custom/store
```

## Step 3: Configure (Optional)

Edit `.db-wiki/config.yaml` to customize settings:

```yaml
# Embedding model (local by default — no API key needed)
embedding:
  provider: local                    # "local" or "openai"
  model_name: all-MiniLM-L6-v2      # 22MB, fast CPU inference
  dimensions: 384

# Learning loop behavior
learning:
  max_gaps_per_run: 10               # Gaps to investigate per run
  decay_rate_weekly: 0.01            # Confidence decay rate

# Web UI
web:
  host: 127.0.0.1
  port: 8080

# Background learning daemon
daemon:
  fast_interval_minutes: 5
  medium_interval_minutes: 60
  deep_interval_minutes: 1440
  adaptive: true                     # Auto-adjusts frequency based on gaps
```

Most defaults work well out of the box.

## Step 4: Connect to a Live Database (Optional)

If you have a SQL Server database you want to query directly:

```bash
db-wiki connect "Server=localhost;Database=MyDB;Trusted_Connection=yes"
```

This enables:
- Data sampling during learning loops
- Live SQL execution with `db-wiki ask --execute`
- System metadata collection

Skip this step if you only have SQL files (DDL, stored procedures).

## Step 5: Ingest DDL Files

Feed your schema definitions into DB Wiki:

```bash
# Single file
db-wiki ingest schema.sql

# Entire directory (recursive)
db-wiki ingest ./sql/tables/

# Force file type if auto-detection fails
db-wiki ingest schema.sql --type ddl
```

DB Wiki extracts:
- Tables with columns, data types, constraints
- Indexes and foreign key relationships
- Schema names and default values

Check what was ingested:

```bash
db-wiki status
```

Example output:

```
 DB Wiki — Knowledge Store Status
+-------------------+-------+
| Metric            | Value |
+-------------------+-------+
| Tables            | 42    |
| Columns           | 387   |
| Procedures        | 0     |
| Relationships     | 28    |
| Schema Coverage   | 12.3% |
| Open Gaps         | 0     |
| Conflicts         | 0     |
+-------------------+-------+
```

## Step 6: Ingest Stored Procedures

```bash
# Directory of SP files
db-wiki ingest ./sql/procedures/ --type sp

# Or let auto-detection handle it
db-wiki ingest ./sql/procedures/
```

DB Wiki parses T-SQL with sqlglot and extracts:
- Table references (reads, writes, joins)
- Call chains between procedures
- IF/ELSE branches and CASE expressions
- Enum values and state transitions

Check procedure details:

```bash
db-wiki sp-info usp_ProcessOrder
```

## Step 7: Run the Learning Loop

Discover knowledge gaps and deepen understanding:

```bash
db-wiki discover --max-gaps 10
```

The learning loop runs 5 phases:

1. **Discover** — detect orphan tables, missing joins, unlabeled enums
2. **Investigate** — sample data, analyze patterns
3. **Reason** — infer relationships, resolve aliases
4. **Validate** — cross-check against existing knowledge
5. **Consolidate** — merge findings, update confidence scores

View what was found:

```bash
db-wiki data-quality
db-wiki lint
```

## Step 8: Search and Query

Search for entities by name or description:

```bash
db-wiki search "orders"
db-wiki search "customer address" --limit 5
```

Ask natural language questions (requires LLM config or live DB):

```bash
# Generate SQL from a question
db-wiki ask "Show me all orders placed in the last 30 days"

# Generate and execute against live DB
db-wiki ask "How many customers signed up this month?" --execute

# Get raw SQL only
db-wiki ask "Revenue by product category" --sql-only
```

## Step 9: Explore and Analyze

```bash
# Trace data lineage
db-wiki lineage Orders --max-depth 3

# Analyze impact of changing a table
db-wiki impact Orders --depth 2

# View state machine for an enum column
db-wiki state-machine Orders Status

# Analyze procedure branches
db-wiki branch-analysis usp_ProcessOrder

# Compare two entities
db-wiki compare Orders Invoices

# Check knowledge coverage
db-wiki coverage
```

## Step 10: Teach and Confirm

Inject tribal knowledge that auto-discovery can't find:

```bash
# Teach a business rule
db-wiki teach table Orders description "Customer purchase orders, created by checkout flow"
db-wiki teach column "Orders.Status" enum_label "5 = fraud hold, 6 = manual review"

# Confirm an auto-discovered fact (sets confidence to 1.0)
db-wiki confirm column "Orders.Status" enum_label "pending"
```

## Step 11: Generate Documentation

```bash
# Explain a table (generates wiki-style markdown)
db-wiki explain Orders

# Explain a procedure
db-wiki explain usp_ProcessOrder --type procedure
```

## Step 12: Export Knowledge

Export the entire knowledge base in multiple formats:

```bash
# All formats at once
db-wiki export

# Specific format
db-wiki export --format markdown
db-wiki export --format mermaid      # ER diagrams
db-wiki export --format json         # JSON schema
db-wiki export --format ddl          # Annotated CREATE TABLE

# Single entity
db-wiki export Orders --format markdown
```

Exports go to `.db-wiki/export/`.

## Step 13: Start the Web UI

Launch the interactive graph visualization and dashboard:

```bash
db-wiki serve
```

Open http://127.0.0.1:8080 in your browser to see:
- **Knowledge Graph** — interactive vis.js network with color-coded nodes
  - Click a node to see wiki details in a side panel
  - Double-click to expand neighbors
  - Confidence shown as node opacity
  - Gap nodes highlighted with dashed borders
- **Dashboard** (at `/dashboard`) — coverage %, gap count, conflict count, growth charts

The background learning daemon starts automatically with `serve`.

For headless mode (learning daemon only, no web UI):

```bash
db-wiki serve --no-ui
```

## Step 14: Share Patterns Across Projects (Optional)

Push discovered patterns to a shared cross-project store:

```bash
# Push patterns from this project
db-wiki push-cross

# View available cross-project patterns
db-wiki pull-cross
db-wiki pull-cross --type naming
db-wiki pull-cross --type enum
```

Patterns stored in `~/.db-wiki/cross.db` are available to all projects with a confidence penalty (20-70% based on similarity).

## Step 15: Register as MCP Server for Claude

Add DB Wiki as an MCP server so Claude can query your database knowledge directly:

Add to your Claude Code MCP config (`~/.claude/mcp_servers.json` or project `.claude/settings.json`):

```json
{
  "mcpServers": {
    "db-wiki": {
      "command": "db-wiki-mcp",
      "args": [],
      "cwd": "/path/to/your/project"
    }
  }
}
```

Or with uv (no global install needed):

```json
{
  "mcpServers": {
    "db-wiki": {
      "command": "uv",
      "args": ["run", "db-wiki-mcp"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

Once registered, Claude has access to 24 tools including `ask`, `search`, `lineage`, `explain`, `discover`, `teach`, and more.

## Quick Reference

| Task | Command |
|------|---------|
| Initialize | `db-wiki init` |
| Connect to DB | `db-wiki connect "connection_string"` |
| Ingest SQL files | `db-wiki ingest path/to/sql/` |
| Check status | `db-wiki status` |
| Search entities | `db-wiki search "query"` |
| Ask questions | `db-wiki ask "natural language question"` |
| Run learning | `db-wiki discover` |
| Teach a fact | `db-wiki teach table Name attribute value` |
| Confirm a fact | `db-wiki confirm table Name attribute value` |
| View lineage | `db-wiki lineage EntityName` |
| Export knowledge | `db-wiki export --format all` |
| Start web UI | `db-wiki serve` |
| Health check | `db-wiki lint` |
| Coverage report | `db-wiki coverage` |
| Share patterns | `db-wiki push-cross` |
| Start MCP server | `db-wiki-mcp` |

## Typical Workflow

```
init → ingest DDL → ingest SPs → discover → teach/confirm → ask → export → serve
```

Run `discover` periodically (or use `db-wiki serve` for automatic background learning) to continuously deepen the knowledge base. The more you teach and confirm, the more accurate the system becomes.
