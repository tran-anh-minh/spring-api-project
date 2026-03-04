---
name: review-code
description: "Validates code against project conventions (CONVENTIONS.md Section 15). Reads changed/new files, checks every rule, outputs structured pass/fail report. Use after writing code or before committing."
risk: low
source: custom
date_added: "2026-03-04"
---

# Review Code — Convention Validator

## Purpose

Automatically validate code against **every rule** in `.claude/plan/CONVENTIONS.md`.
Produces a structured report so violations are caught before they become technical debt.

This is **Layer 2 (VERIFY)** of the convention enforcement system.

---

## Operating Mode

You are a **strict code auditor**. You check code against documented conventions — nothing more, nothing less.

- Do NOT fix code (unless asked to after the review)
- Do NOT add features or refactor
- Do NOT invent rules that aren't in CONVENTIONS.md
- Report ONLY violations of documented conventions with section references

---

## The Process

### Step 1: Read Conventions

Read `.claude/plan/CONVENTIONS.md` in full. This is your **only source of truth** for what's correct.

### Step 2: Identify Files to Review

Determine scope based on how the skill was invoked:

| Invocation | Scope |
|------------|-------|
| `/review-code` (no args) | All files changed since last commit (`git diff --name-only`) |
| `/review-code module/user/` | All files in the specified path |
| `/review-code UserService.java` | Specific file |
| `/review-code --all` | All Java source files in the project |

If not in a git repo or no changes detected, ask the user which files to review.

### Step 3: Check Each File

For every file in scope, run the applicable checks from Section 15 of CONVENTIONS.md.

**Determine which checks apply based on file type:**

| File Pattern | Apply These Checks |
|-------------|-------------------|
| `**/core/**/*.java` | 15.1 (core must not import module/) |
| `**/*Entity.java`, `**/User.java`, `**/Course.java` etc. | 15.1 (no framework deps), 15.8 (date/time) |
| `**/*Service.java` | 15.1 (cross-module), 15.5 (logging), 15.7 (transactions) |
| `**/*Controller.java` | 15.1 (thin), 15.2 (DTOs), 15.6 (API consistency), 15.4 (security) |
| `**/*Mapper.java` | 15.1 (mapper rules) |
| `**/*Mapper.xml` | 15.3 (SP checks — CALLABLE, no inline SQL, naming) |
| `**/dto/*.java` | 15.2 (DTO checks — naming, location, validation) |
| `**/schema-h2.sql` | 15.3 (SP naming, p_ prefix) |
| Any `.java` file with `log.` | 15.5 (logging checks) |

### Step 4: Generate Report

Output the report in this exact format:

```
## Convention Review Report

**Scope:** [files reviewed]
**Date:** [current date]
**Conventions version:** CONVENTIONS.md (15 sections)

---

### Summary

| Severity | Count |
|----------|-------|
| BLOCKER  | X     |
| HIGH     | X     |
| MEDIUM   | X     |
| LOW      | X     |
| **TOTAL**| **X** |

**Result:** PASS ✓ / FAIL ✗ (FAIL if any BLOCKER or HIGH exists)

---

### Violations

#### BLOCKER

**[B1] Section 15.1 — Entity imports Spring framework**
- File: `module/user/User.java:3`
- Found: `import org.springframework.data.annotation.Id;`
- Rule: Entity must have ZERO framework dependencies (Section 1.2)
- Fix: Remove Spring import. Use plain Java field with no annotation.

#### HIGH

**[H1] Section 15.3 — Mapper XML uses inline SQL**
- File: `resources/mapper/user/UserMapper.xml:12`
- Found: `<select id="findByUsrNo" resultType="User">SELECT * FROM users...</select>`
- Rule: ALL DB access through stored procedures (Section 1.2)
- Fix: Change to `<select id="findByUsrNo" statementType="CALLABLE">{CALL sp_user_find_by_usr_no(#{usrNo})}</select>`

#### MEDIUM

**[M1] Section 15.5 — Missing module log prefix**
- File: `module/user/UserService.java:45`
- Found: `log.info("User created | usrNo={}", usrNo);`
- Rule: Use module prefix [USER] (Section 5.5)
- Fix: `log.info("[USER] User created | usrNo={}", usrNo);`

#### LOW

(none)

---

### Files Passed (no violations)
- `module/user/dto/UserRequest.java` ✓
- `module/user/dto/UserResponse.java` ✓

---

### Checklist Applied

- [x] 15.1  Layer & module violations
- [x] 15.2  DTO checks
- [x] 15.3  Stored procedure checks
- [x] 15.4  Security checks
- [x] 15.5  Logging checks
- [x] 15.6  API consistency checks
- [x] 15.7  Transaction checks
- [x] 15.8  Date/time checks
- [x] 15.9  Pagination checks
- [ ] 15.10 Module completeness (only for new modules)
```

### Step 5: Offer Next Steps

After the report, ask:

> **What would you like to do?**
> 1. Fix all violations automatically
> 2. Fix only BLOCKERs and HIGHs
> 3. I'll fix manually
> 4. Report a convention gap → use `/update-convention`

---

## Checking Rules — Detailed

### 15.1 — Layer & Module Violation Checks

**For `core/` files:**
- Scan imports: FAIL if any import contains `module.`

**For entity files (files that are domain models, NOT DTOs, NOT Services):**
- Scan imports: FAIL if any import contains `org.springframework`, `org.apache.ibatis`, `org.mybatis`
- Scan annotations: FAIL if class has `@Data` (allow `@Getter`, `@Setter`, `@Builder`, `@NoArgsConstructor`, `@AllArgsConstructor`)
- Scan annotations: FAIL if any method has `@Select`, `@Insert`, `@Update`, `@Delete`, `@Mapper`

**For service files:**
- Scan imports: FAIL if importing another module's Mapper (e.g., `module.course.CourseMapper` in `UserService`)
- Scan annotations: CHECK for `@Transactional` presence (see 15.7)

**For controller files:**
- Scan method bodies: WARN if method body > 10 lines (likely has business logic)
- Scan return types: FAIL if method returns anything not wrapped in `ApiResponse<>`
- Scan method params: WARN if `@RequestBody` without `@Valid` or `@Validated`

**For mapper XML files:**
- Scan for `SELECT`, `INSERT`, `UPDATE`, `DELETE` without `statementType="CALLABLE"`
- Scan for missing `{CALL sp_` pattern

### 15.3 — SP Naming Check

- SP names must match pattern: `sp_{module}_{action}`
- Parameters must be prefixed with `p_`
- Verify in both `schema-h2.sql` and mapper XML files

### 15.5 — Logging Checks

- Scan for string concatenation in log calls: `log.xxx("msg" + var)` → FAIL
- Scan for module prefix: `log.xxx("[` → must start with module prefix
- Scan for `log.error(` calls: last parameter should be exception variable (heuristic: variable name ending in `e`, `ex`, `exception`, or `Exception` type)
- Scan for sensitive terms in log strings: `password`, `token`, `apiKey`, `secret` → WARN

### 15.7 — Transaction Checks

- Service methods with GET/find/search/list in name: should have `@Transactional(readOnly = true)`
- Service methods with create/update/delete/save in name: should have `@Transactional`
- Controllers with `@Transactional`: FAIL (wrong layer)
- Private methods with `@Transactional`: FAIL (won't work)

---

## Special Modes

### New Module Review

When a new module is detected (folder under `module/` that didn't exist before), also run the **Module Completeness Check (Section 15.10)**:

Verify all items in Section 3.3 checklist exist:
- Entity, enums, SP in schema, mapper interface, mapper XML, service, controller, DTOs, error codes, swagger tag

### Quick Review

If invoked as `/review-code --quick`, only check BLOCKERs (15.1 layer violations, inline SQL, entity framework deps).

---

## When to Use

- **After writing any code** — before marking a task as done
- **Before committing** — catch violations early
- **When reviewing PR/changes** — structured review instead of ad-hoc
- **Periodically on full codebase** — `/review-code --all` to catch drift

## When NOT to Use

- On non-Java files (config, markdown, etc.)
- During brainstorming/design phase (no code to review)
- On test files (test conventions are lighter)
