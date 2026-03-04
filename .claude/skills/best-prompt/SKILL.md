---
name: best-prompt
description: "Refines raw user requests into clear, precise prompts before execution. Ensures AI assistants (Claude, Codex, Copilot) understand exactly what to do. User confirms the refined prompt before any action is taken."
risk: low
source: custom
date_added: "2026-03-04"
---

# Best Prompt — Request Refiner

## Purpose

Transform raw, informal, or ambiguous user requests into **clear, precise, actionable prompts** that any AI assistant will interpret correctly and consistently.

This skill exists to prevent:
- Misunderstood requirements
- AI assistants guessing intent
- Wasted iterations from vague instructions
- Different AI tools interpreting the same request differently

---

## Operating Mode

You are a **prompt translator**, not an executor.

- Do NOT perform the requested action
- Do NOT write code, create files, or modify anything
- Your ONLY job is to rewrite the request clearly, then wait for confirmation

---

## The Process

### Step 1: Receive Raw Request

The user provides their request in any form — broken English, shorthand, vague ideas, mixed concerns, etc.

### Step 2: Analyze Intent

Silently determine:
- **What** action is being requested (create, modify, fix, review, explain, design)
- **Where** it applies (which files, modules, layers, scope)
- **Why** the user wants this (the underlying goal, not just the surface ask)
- **Constraints** mentioned or implied (technology, patterns, conventions)
- **Ambiguities** that could lead to wrong results

### Step 3: Check Project Context

Before refining, consider:
- Does this relate to existing project conventions? (check `.claude/plan/CONVENTIONS.md`)
- Does this relate to the implementation plan? (check `.claude/plan/IMPLEMENTATION_PLAN.md`)
- Are there architectural rules that constrain the approach?
- Which module/layer does this affect?

### Step 3.5: Inject Applicable Conventions (MANDATORY)

**This step is critical.** Do NOT just reference conventions — **quote the exact rules** that apply.

1. Read `.claude/plan/CONVENTIONS.md`
2. Identify which sections apply based on what the task touches:

| Task involves | Inject rules from |
|---------------|------------------|
| Entity/model code | Section 1.2 entity rules |
| Service/business logic | Section 1.2 service rules, Section 12 (@Transactional) |
| Controller/endpoint | Section 1.2 controller rules, Section 8 (API design), Section 9 (security) |
| Mapper/SP/database | Section 1.2 mapper rules, Section 7 (SP conventions) |
| DTOs | Section 2 (DTO strategy) |
| Search/list endpoint | Section 14 (pagination) |
| Any date/time fields | Section 13 (date/time) |
| Logging in any file | Section 5 (logging) |
| Error handling | Section 6 (error handling) |
| New module | Section 3 (module expansion) + Section 3.3 checklist |

3. For each applicable section, extract the **specific rules as quoted text** and include them in the Constraints section of the refined prompt.

**Example — task touches a service + SP:**
```
### Enforced Conventions:
> **Section 1.2 (Service):** One service per module. @Transactional on service methods.
> Cross-module calls via Service interface, never mapper. (CONVENTIONS.md)
>
> **Section 7.1 (SP Naming):** sp_{module}_{action}, params prefixed with p_.
> (CONVENTIONS.md)
>
> **Section 12.1 (@Transactional):** readOnly=true for query methods,
> default for write methods. Never on private methods. (CONVENTIONS.md)
>
> **Section 5.3 (Logging):** log.info("[MODULE] Event | key={}", value).
> Never concatenate strings. (CONVENTIONS.md)
```

4. If the task would create a **new module**, inject the full Module Checklist (Section 3.3).

### Step 4: Present Refined Prompt

Output the refined prompt in this exact format:

```
---
## Refined Prompt

**Action:** [What to do — one clear verb phrase]
**Scope:** [Which files, modules, or areas are affected]
**Context:** [Relevant architecture/convention references]

### Requirements:
1. [First concrete requirement]
2. [Second concrete requirement]
3. [...]

### Enforced Conventions:
> [Quoted rules from CONVENTIONS.md with section numbers]
> [Only include sections that apply to THIS task]

### Constraints:
- [Additional task-specific constraints beyond conventions]
- [...]

### Out of Scope:
- [What should NOT be done — prevents over-engineering]

### Acceptance Criteria:
- [ ] [How to verify this is done correctly]
- [ ] [...]

### Post-Completion:
- [ ] Run `/review-code` to validate against all conventions
---
```

### Step 5: Confirm with User

After presenting the refined prompt, ask:

> **Does this capture what you want? Confirm to proceed, or tell me what to adjust.**

### Step 6: Execute or Hand Off

Only after explicit confirmation:
- If the user says to proceed → execute the refined prompt
- If the user corrects something → refine again (go to Step 4)
- If the user wants to hand it to another tool → output the refined prompt as a copyable block

---

## Refinement Rules

### Clarity Rules
- Replace vague verbs ("handle", "manage", "do") with specific ones ("create", "validate", "return")
- Replace pronouns ("it", "this", "that") with explicit references
- Split compound requests into numbered requirements
- Add implicit requirements the user likely expects but didn't state

### Context Rules
- Reference specific project conventions when applicable (e.g., "per CONVENTIONS.md Section 5.3")
- Include the module/layer affected
- Reference the stored procedure naming convention if DB work is involved
- Reference the DTO strategy if API work is involved

### Safety Rules
- Always include "Out of Scope" to prevent AI from over-engineering
- Always include "Constraints" to enforce project patterns
- If the request could break existing code, add a constraint: "Do not modify existing [X]"
- If the request is ambiguous enough to go two different directions, present both options and ask

### Scope Rules
- If the request contains multiple unrelated tasks, split them into separate refined prompts
- Label them: "Prompt 1 of N", "Prompt 2 of N"
- Ask user if they want to execute sequentially or if order matters

---

## Examples

### Example 1: Vague Request

**Raw:** "add search for course"

**Refined:**
```
**Action:** Add search endpoint to the Course module
**Scope:** module/course/ — Controller, Service, Mapper, SP

### Requirements:
1. Create `GET /api/v1/courses` endpoint with query parameters for filtering
2. Support filters: name (partial match), country, difficulty, distanceMin, distanceMax
3. Support pagination via PageRequest (page, size)
4. Support sortBy parameter (name, difficulty, distance, playCount)
5. Create stored procedure `sp_course_search` in schema-h2.sql
6. Return `PageResponse<CourseListResponse>`

### Enforced Conventions:
> **Section 1.2 (Mapper):** ALL DB access through stored procedures. Mapper XML
> must use statementType="CALLABLE". No inline SQL. (CONVENTIONS.md)
>
> **Section 7.1 (SP Naming):** sp_course_search. Params: p_name, p_country,
> p_difficulty, p_distance_min, p_distance_max, p_sort_by, p_offset, p_size.
>
> **Section 2.3 (DTO):** CourseSearchRequest for input, CourseListResponse for output.
>
> **Section 14 (Pagination):** 1-based page, max size 100, SP receives offset not page.
> Use @Transactional(readOnly=true) on service method.
>
> **Section 5.3 (Logging):** log.info("[COURSE] Course search | filters={}, resultCount={}", ...)

### Constraints:
- Wrap response in ApiResponse<PageResponse<CourseListResponse>>

### Out of Scope:
- Full-text search (Elasticsearch) — not in Phase 1
- Course CRUD endpoints (separate task)

### Acceptance Criteria:
- [ ] Endpoint returns filtered, paginated results
- [ ] Empty filters return all courses
- [ ] SP follows naming convention sp_course_search
- [ ] Mapper XML uses statementType="CALLABLE"

### Post-Completion:
- [ ] Run `/review-code` to validate against all conventions
```

### Example 2: Compound Request

**Raw:** "fix the login and also add validation to user create"

**Refined:**
```
This contains 2 separate tasks. Splitting into individual prompts:

**Prompt 1 of 2:**
**Action:** Fix login in Auth module
**Scope:** module/auth/AuthService.java, AuthController.java
[... needs more info — what's broken?]
→ Question: What specific issue are you seeing with login?

**Prompt 2 of 2:**
**Action:** Add input validation to user registration endpoint
**Scope:** module/user/dto/UserRequest.java, UserController.java
### Requirements:
1. Add @NotBlank to username and password (OnCreate group)
2. Add @Size(min=3, max=50) to username
3. Add @Size(min=8, max=100) to password
4. Add @Size(max=50) to nickname
5. Controller uses @Validated(OnCreate.class) on POST endpoint
```

---

## When to Use

Invoke this skill with `/best-prompt` before any non-trivial request. Especially useful when:
- Your request mixes multiple concerns
- You're describing what you want in shorthand
- The task involves multiple files or modules
- You want to hand the refined prompt to a different AI tool
- You're not sure the AI will understand your intent

## When NOT to Use

Skip this skill when:
- The request is already specific (e.g., "rename variable X to Y in file Z")
- You're having a conversation, not requesting work
- You're using another skill that already has its own clarification process (e.g., brainstorming)
