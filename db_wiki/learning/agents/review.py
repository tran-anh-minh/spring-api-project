"""Review Agent — validates findings before they reach the knowledge store.

Implements the Validate phase of the learning loop. Quality-gates findings
by checking evidence quality, confidence thresholds, and entity validity.
When an LLM is configured, asks it to evaluate findings. Otherwise uses
deterministic heuristic rules (D-01 / AGENT-02).
"""

from __future__ import annotations

import json
import logging
import sqlite3

from db_wiki.learning.agents.base import call_llm
from db_wiki.learning.models import AgentFindings, FindingItem, GapRecord

logger = logging.getLogger(__name__)


def _entity_exists(conn: sqlite3.Connection, entity_name: str) -> bool:
    """Check if the entity's table exists in the knowledge store."""
    parts = entity_name.split(".", 1)
    table_name = parts[0]

    row = conn.execute(
        "SELECT 1 FROM current_db_tables WHERE table_name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _review_with_llm(
    gap: GapRecord,
    findings: AgentFindings,
    config,
) -> AgentFindings | None:
    """Attempt LLM-powered review. Returns None if unavailable."""
    findings_json = json.dumps(
        [item.model_dump() for item in findings.items]
    )
    prompt = (
        f"Review these findings for a SQL Server knowledge gap:\n"
        f"Gap: {gap.gap_type} for {gap.entity_name}\n"
        f"Evidence quality: {findings.evidence_quality}\n"
        f"Findings: {findings_json}\n\n"
        f"For each finding, respond with JSON array of objects containing:\n"
        f"  - index (0-based), approved (true/false), reason (string)\n"
        f"Only approve findings that are well-supported by evidence."
    )

    response = call_llm(prompt, config)
    if response is None:
        return None

    try:
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        decisions = json.loads(text)

        approved_indices = {
            d["index"] for d in decisions if d.get("approved", False)
        }
        approved_items = [
            item for i, item in enumerate(findings.items)
            if i in approved_indices
        ]

        return AgentFindings(
            items=approved_items,
            summary=f"LLM review: approved {len(approved_items)} of {len(findings.items)} items",
            evidence_quality=findings.evidence_quality,
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("Failed to parse LLM review response")
        return None


def _review_heuristic(
    conn: sqlite3.Connection,
    findings: AgentFindings,
) -> AgentFindings:
    """Deterministic heuristic review for offline mode."""
    approved: list[FindingItem] = []
    rejected = 0

    for item in findings.items:
        # Reject items with very low confidence
        if item.confidence < 0.1:
            rejected += 1
            continue

        # Reject empty values
        if not item.value or not item.value.strip():
            rejected += 1
            continue

        # For low evidence quality, require higher confidence
        if findings.evidence_quality < 0.5 and item.confidence < 0.3:
            rejected += 1
            continue

        # Check entity exists (soft check — don't reject if table lookup fails)
        try:
            if not _entity_exists(conn, item.entity_name):
                logger.debug(
                    "Entity %s not found in knowledge store, keeping with warning",
                    item.entity_name,
                )
        except Exception:
            pass  # Table might not exist yet — don't block

        approved.append(item)

    return AgentFindings(
        items=approved,
        summary=f"Approved {len(approved)} of {len(approved) + rejected} items",
        evidence_quality=findings.evidence_quality,
    )


def review_findings(
    conn: sqlite3.Connection,
    gap: GapRecord,
    findings: AgentFindings,
    config,
) -> AgentFindings:
    """Validate findings quality before they are applied to the store.

    Args:
        conn: SQLite knowledge store connection.
        gap: The knowledge gap these findings address.
        findings: Research findings to validate.
        config: DBWikiConfig with learning settings.

    Returns:
        AgentFindings containing only approved items.
    """
    # Hard reject: evidence quality too low
    if findings.evidence_quality < 0.2:
        return AgentFindings(
            items=[],
            summary=f"Rejected all: evidence quality {findings.evidence_quality:.2f} below threshold 0.2",
            evidence_quality=findings.evidence_quality,
        )

    # Try LLM review if configured
    llm_result = _review_with_llm(gap, findings, config)
    if llm_result is not None:
        return llm_result

    # Fall back to heuristic review
    return _review_heuristic(conn, findings)
