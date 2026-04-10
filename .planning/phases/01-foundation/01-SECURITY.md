# Security Audit — Phase 01: Foundation

**Audited:** 2026-04-10
**ASVS Level:** 1
**Threats Closed:** 11/11
**Threats Open:** 0/11

---

## Threat Verification

| Threat ID | Category | Component | Disposition | Status | Evidence |
|-----------|----------|-----------|-------------|--------|----------|
| T-01-01 | Tampering | store.py open_store | mitigate | CLOSED | `db_wiki/core/store.py:23` — `abs_path = Path(db_path).resolve()` before `sqlite3.connect(str(abs_path))` |
| T-01-02 | Tampering | config.py load_config | mitigate | CLOSED | `db_wiki/core/config.py:59` — `yaml.safe_load(text)`; pydantic `DBWikiConfig.model_validate(data)` at line 62 |
| T-01-03 | Denial of Service | config.py load_config | accept | CLOSED | Accepted: config files are small and local-only; no network exposure; user controls their own files |
| T-01-04 | Information Disclosure | store.py knowledge.db | accept | CLOSED | Accepted: single-user local tool; DB file permissions managed by OS; no network-accessible path |
| T-02-01 | Denial of Service | ddl_parser.py parse_ddl_file | mitigate | CLOSED | `db_wiki/ingest/ddl_parser.py:34-51` — `check_file_size_limit()` enforces `max_mb * 1024 * 1024` byte limit with `ValueError` |
| T-02-02 | Tampering | ddl_parser.py ingest_ddl | mitigate | CLOSED | `db_wiki/ingest/ddl_parser.py:397-510` — all INSERT statements use `?` parameterized placeholders; no string formatting of user data into SQL |
| T-02-03 | Tampering | ddl_parser.py parse_ddl_file | accept | CLOSED | Accepted: sqlglot parses SQL into AST structurally; no SQL is executed against any database; malicious DDL content is harmless |
| T-03-01 | Tampering | cli/app.py init --store-path | mitigate | CLOSED | `db_wiki/cli/app.py:44` — `store_path = store_path.resolve()` in `init()`; also present in `connect()` at line 84 and `ingest()` at line 123 |
| T-03-02 | Tampering | server/app.py ingest tool | mitigate | CLOSED | `db_wiki/server/app.py:70-76` — `Path(file_path).resolve()`, `path.exists()`, and `path.is_file()` checks before reading |
| T-03-03 | Denial of Service | server/app.py ingest tool | mitigate | CLOSED | `db_wiki/server/app.py:79-88` — file size checked against `config.ingest.max_file_size_mb * 1024 * 1024`; raises `ValueError` if exceeded |
| T-03-04 | Information Disclosure | cli/app.py connect | accept | CLOSED | Accepted: connection string stored in plaintext in config.yaml; local-only tool; OS file permissions protect the file; trade-off documented |

---

## Accepted Risks Log

| Threat ID | Risk | Rationale | Review Trigger |
|-----------|------|-----------|----------------|
| T-01-03 | Large local config.yaml could slow config loading | Config files are user-controlled and local; no network path exists to deliver oversized files | If config loading becomes user-facing (e.g., API endpoint) |
| T-01-04 | knowledge.db contains schema metadata readable by OS users with file access | Single-user local tool; no credentials or PII are stored in Phase 1; OS permissions govern access | If multi-user deployment or sensitive metadata added in future phases |
| T-02-03 | Malicious SQL in DDL input files | sqlglot builds an AST — DDL is never executed; attacker cannot run SQL against any database via this path | If execution of parsed SQL is ever added |
| T-03-04 | Connection string (potentially containing credentials) stored in plaintext in config.yaml | Local-only tool; ASVS L1 accepts OS-managed file permissions for local secrets; no credential transmission | If tool gains network-accessible endpoints or multi-user support |

---

## Unregistered Threat Flags

None. SUMMARY.md `## Threat Flags` sections for all three plans report no new threat surface beyond the declared threat model.

- 01-01-SUMMARY.md: "No new threat surface beyond what was planned in the threat model."
- 01-02-SUMMARY.md: No threat flags section; all T-02-xx mitigations noted as implemented.
- 01-03-SUMMARY.md: "No new threat surface beyond the plan's threat model. T-03-01 through T-03-04 mitigations applied as specified."
