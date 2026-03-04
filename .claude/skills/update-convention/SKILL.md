---
name: update-convention
description: "Evolves project conventions when gaps are found. Reads current CONVENTIONS.md, proposes new rules with good/bad examples, adds review checks to Section 15. User confirms before any change is made."
risk: low
source: custom
date_added: "2026-03-04"
---

# Update Convention — Convention Evolver

## Purpose

Safely evolve `.claude/plan/CONVENTIONS.md` when a gap is discovered — a pattern that should be documented but isn't, or an existing rule that needs correction.

This is **Layer 3 (EVOLVE)** of the convention enforcement system.

---

## Operating Mode

You are a **convention editor**, not a code writer.

- Read the full current CONVENTIONS.md before making any changes
- NEVER change conventions without user confirmation
- NEVER remove existing conventions without explicit request
- NEVER add conventions that contradict existing ones (flag the conflict instead)
- Keep the same formatting and structure as existing sections

---

## The Process

### Step 1: Understand the Gap

The user describes a convention gap. This typically comes from:
- `/review-code` finding an issue not covered by current conventions
- A recurring pattern noticed across multiple modules
- A decision that was made but never documented
- An existing convention that turned out to be wrong or incomplete

Ask if not clear:
> What specific pattern or rule needs to be documented? Can you give an example of code that should be correct vs. incorrect?

### Step 2: Read Current Conventions

Read `.claude/plan/CONVENTIONS.md` in full to:
- Identify which section the new convention belongs in
- Check if a related convention already exists (update, not duplicate)
- Verify the new rule doesn't contradict existing rules

### Step 3: Propose the Convention

Present the proposed addition in this format:

```
## Proposed Convention Change

**Type:** New rule / Update existing rule / Remove outdated rule
**Section:** [Where it belongs — e.g., "Section 5 (Logging)" or "New Section 16"]
**Trigger:** [What caused this gap to be identified]

### Rule:
[The convention statement — clear, imperative]

### Example — Good:
```java
[Code that follows the convention]
```

### Example — Bad:
```java
[Code that violates the convention]
```

### Review Check (for Section 15):
| Check | What to Look For |
|-------|-----------------|
| [Check description] | [What constitutes a violation] |

### Impact:
- Affected files: [Which existing files would need to change, if any]
- Risk: [None / Low / Medium — does this break existing patterns?]
```

### Step 4: Confirm with User

> **Does this convention look correct? Confirm to add it to CONVENTIONS.md, or adjust.**

### Step 5: Apply the Change

Only after explicit confirmation:

1. Add the convention to the appropriate section in CONVENTIONS.md
2. Add the corresponding review check to Section 15
3. If the convention affects the module checklist (Section 3.3), update it
4. If the convention should be referenced in CLAUDE.md, update the summary

### Step 6: Verify Consistency

After applying, re-read CONVENTIONS.md and verify:
- No contradictions with existing rules
- Section numbers are still sequential
- Review checklist (Section 15) references correct section numbers
- CLAUDE.md summary still accurate

Report:
> Convention updated. Section [X] now includes [rule summary]. Review check 15.X added.

---

## Safety Rules

### When Adding a New Convention
- Must include at least one Good and one Bad example
- Must include a corresponding Section 15 review check
- Must not contradict existing conventions (if it does, flag the conflict and let the user decide which to keep)

### When Updating an Existing Convention
- Show the diff: what changed from the old rule to the new rule
- If the change would make existing code non-compliant, list the affected files
- User must acknowledge the impact before the change is applied

### When Removing a Convention
- Explain why it's being removed
- Check if any review checks reference it (remove those too)
- Check if CLAUDE.md references it (update if needed)

### When Conventions Conflict
If a proposed convention contradicts an existing one:

```
## Conflict Detected

**Proposed:** [New rule]
**Existing:** Section X.Y — [Current rule]
**Conflict:** [How they contradict]

Options:
1. Keep existing, discard proposed
2. Replace existing with proposed
3. Merge into a unified rule
```

---

## Common Gap Types

| Gap Type | How to Handle |
|----------|--------------|
| Missing pattern | Add to most relevant existing section |
| Wrong example | Update the example in the existing section |
| Outdated rule | Update the rule, note what changed |
| New technology | Create new section (e.g., "Section 16: Kafka Conventions") |
| Scope change | Update affected sections + review checks |
| Naming inconsistency | Update naming table in Section 11 |

---

## When to Use

- After `/review-code` reports a gap (no convention covers the issue)
- When a team member asks "what's the convention for X?" and there's no answer
- When a decision from brainstorming/design should become a permanent convention
- When migrating to a new technology or pattern that needs documentation

## When NOT to Use

- For one-off exceptions (don't add a convention for a single edge case)
- For project-specific config (that belongs in IMPLEMENTATION_PLAN.md)
- For temporary workarounds (document in code comments instead)
