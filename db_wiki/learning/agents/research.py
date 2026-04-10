"""Research Agent — investigates knowledge gaps using LLM or heuristics.

Implements the Investigate+Reason phases of the learning loop.
When an LLM is configured, builds a structured prompt and parses JSON findings.
Falls back to deterministic heuristic analysis in offline mode (D-01/D-03).
"""

from __future__ import annotations

import json
import logging
import sqlite3

from db_wiki.learning.agents.base import call_llm
from db_wiki.learning.models import AgentFindings, FindingItem, GapRecord

logger = logging.getLogger(__name__)


def _gather_context(conn: sqlite3.Connection, entity_name: str) -> str:
    """Gather related entity context from the knowledge store."""
    try:
        from db_wiki.search.hybrid import hybrid_search
        from db_wiki.core.config import EmbeddingConfig

        results = hybrid_search(conn, entity_name, EmbeddingConfig(), limit=5)
        if results:
            return "; ".join(f"{r[0]} (score={r[2]:.2f})" for r in results)
    except Exception:
        logger.debug("hybrid_search unavailable, using basic context")

    # Fallback: check if entity exists in current tables
    parts = entity_name.split(".", 1)
    table_name = parts[0]
    rows = conn.execute(
        "SELECT table_name, column_name FROM current_enum_values WHERE table_name = ? LIMIT 5",
        (table_name,),
    ).fetchall()
    if rows:
        return "; ".join(f"{r['table_name']}.{r['column_name']}" for r in rows)

    return "No related context found"


def _research_with_llm(
    gap: GapRecord,
    evidence: AgentFindings,
    context: str,
    config,
) -> AgentFindings | None:
    """Attempt LLM-powered research. Returns None if LLM unavailable."""
    evidence_items = json.dumps(
        [item.model_dump() for item in evidence.items[:10]]
    )
    prompt = (
        f"Analyze this knowledge gap in a SQL Server database:\n"
        f"Gap: {gap.gap_type} for {gap.entity_name}\n"
        f"Description: {gap.description}\n"
        f"Evidence collected: {evidence.summary}\n"
        f"Evidence items: {evidence_items}\n"
        f"Related entities: {context}\n\n"
        f"Provide structured findings as JSON array of objects with keys: "
        f"entity_type, entity_name, attribute, value, confidence (0.0-1.0).\n"
        f"Only include findings supported by the evidence."
    )

    response = call_llm(prompt, config)
    if response is None:
        return None

    try:
        # Extract JSON from response (may be wrapped in markdown code block)
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(text)

        items = []
        for obj in parsed:
            items.append(
                FindingItem(
                    entity_type=obj.get("entity_type", gap.entity_type),
                    entity_name=obj.get("entity_name", gap.entity_name),
                    attribute=obj.get("attribute", "description"),
                    value=str(obj.get("value", "")),
                    # Cap LLM-derived confidence at 0.7 (T-03-08)
                    confidence=min(0.7, float(obj.get("confidence", 0.5))),
                    source="llm_research",
                )
            )

        return AgentFindings(
            items=items,
            summary=f"LLM research produced {len(items)} findings",
            evidence_quality=0.7,
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.warning("Failed to parse LLM response as JSON")
        return None


def _research_heuristic(
    gap: GapRecord,
    evidence: AgentFindings,
) -> AgentFindings:
    """Deterministic heuristic analysis for offline mode."""
    items: list[FindingItem] = []

    if gap.gap_type == "unlabeled_enum":
        # Use evidence samples as potential enum labels
        for item in evidence.items:
            items.append(
                FindingItem(
                    entity_type=gap.entity_type,
                    entity_name=gap.entity_name,
                    attribute="enum_label",
                    value=item.value,
                    confidence=0.4,
                    source="heuristic_enum_from_sampling",
                )
            )
        summary = f"Heuristic: {len(items)} enum values from sampling"

    elif gap.gap_type == "orphan_table":
        items.append(
            FindingItem(
                entity_type=gap.entity_type,
                entity_name=gap.entity_name,
                attribute="description",
                value="Potentially unused table — no SP references found",
                confidence=0.3,
                source="heuristic_orphan",
            )
        )
        summary = "Heuristic: flagged as potentially unused"

    elif gap.gap_type == "missing_fk":
        for item in evidence.items:
            items.append(
                FindingItem(
                    entity_type="relationship",
                    entity_name=gap.entity_name,
                    attribute="fk_inferred",
                    value=item.value,
                    confidence=0.4,
                    source="heuristic_fk_from_sampling",
                )
            )
        summary = f"Heuristic: {len(items)} potential FK relationships from sampling"

    elif gap.gap_type == "coverage_gap":
        items.append(
            FindingItem(
                entity_type=gap.entity_type,
                entity_name=gap.entity_name,
                attribute="description",
                value="[Auto-generated: requires human review]",
                confidence=0.2,
                source="heuristic_coverage",
            )
        )
        summary = "Heuristic: placeholder description generated"

    else:
        summary = f"No heuristic available for {gap.gap_type}"

    return AgentFindings(
        items=items,
        summary=summary,
        evidence_quality=0.3 if items else 0.0,
    )


def research_gap(
    conn: sqlite3.Connection,
    gap: GapRecord,
    evidence: AgentFindings,
    config,
) -> AgentFindings:
    """Investigate a knowledge gap using LLM or heuristic analysis.

    Args:
        conn: SQLite knowledge store connection.
        gap: The knowledge gap to investigate.
        evidence: Evidence collected by the Collector Agent.
        config: DBWikiConfig with learning settings.

    Returns:
        AgentFindings with structured research results.
    """
    context = _gather_context(conn, gap.entity_name)

    # Try LLM first if configured
    llm_result = _research_with_llm(gap, evidence, context, config)
    if llm_result is not None:
        return llm_result

    # Fall back to heuristic analysis
    return _research_heuristic(gap, evidence)
