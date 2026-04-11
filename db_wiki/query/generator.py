"""SQL generator for the NL-to-SQL pipeline.

Generates T-SQL queries either via an LLM prompt (when provider is configured)
or via offline templates for tier 1-2 queries (lookup, aggregation).

Security note (T-04-03): User question is embedded in the LLM prompt as plain
text with explicit "Generate T-SQL only" instruction. LLM output always goes
through validate_sql() (in validator.py) before any execution.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from db_wiki.learning.agents.base import call_llm

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """Result of SQL generation."""

    sql: str | None  # Generated SQL, or None if template can't handle the tier
    prompt_used: str  # The prompt sent to LLM, or "" for template generation
    from_template: bool  # True if generated offline via template


# System instruction for LLM SQL generation
SQL_SYSTEM_PROMPT = (
    "You are a T-SQL query generator for SQL Server. "
    "Generate only the SQL query — no explanation. "
    "Use T-SQL syntax: TOP N instead of LIMIT, GETDATE() not NOW(), "
    "square bracket quoting for reserved words."
)


def build_generation_prompt(
    question: str,
    tier: str,
    context_text: str,
    metrics: list | None = None,
    previous_error: str | None = None,
) -> str:
    """Build the full LLM prompt for SQL generation.

    Sections:
      - System instruction (T-SQL only, SQL Server syntax)
      - Schema Context section
      - Defined Metrics section (if metrics provided)
      - Question + tier
      - Retry error section (if previous_error provided)
      - Final instruction: "Generate T-SQL only."

    Args:
        question: The natural language question to answer with SQL.
        tier: The query tier (lookup, aggregation, etc.)
        context_text: Schema context from assemble_context() (L0/L1/L2 blocks).
        metrics: Optional list of metric dicts with 'name' and 'formula' keys.
        previous_error: Error from a previous SQL attempt (enables retry mode).

    Returns:
        The complete prompt string to send to the LLM.
    """
    parts: list[str] = [SQL_SYSTEM_PROMPT, ""]

    parts.append("== Schema Context ==")
    parts.append(context_text)
    parts.append("")

    if metrics:
        parts.append("== Defined Metrics ==")
        for metric in metrics:
            name = metric.get("name", "")
            formula = metric.get("formula", "")
            parts.append(f"  {name}: {formula}")
        parts.append("")

    parts.append(f"Question: {question}")
    parts.append(f"Query tier: {tier}")
    parts.append("")

    if previous_error:
        parts.append(
            f"Previous attempt failed with error: {previous_error}. "
            "Rewrite the query to fix this."
        )
        parts.append("")

    parts.append("Generate T-SQL only.")

    return "\n".join(parts)


def generate_sql(
    question: str,
    tier: str,
    context_text: str,
    config,
    metrics: list | None = None,
    previous_error: str | None = None,
) -> GenerationResult:
    """Generate SQL for the given question using LLM or offline template fallback.

    Tries LLM generation first when config.learning.llm_provider is set.
    Falls back to generate_sql_template() when:
      - LLM is not configured
      - call_llm returns None (offline mode or network error)

    Args:
        question: The natural language question to answer with SQL.
        tier: The query tier string (e.g. "lookup", "aggregation").
        context_text: Schema context from assemble_context().
        config: DBWikiConfig instance.
        metrics: Optional list of defined metric dicts.
        previous_error: Error from a previous attempt (triggers retry prompt).

    Returns:
        GenerationResult with sql, prompt_used, and from_template flag.
    """
    llm_provider = getattr(getattr(config, "learning", None), "llm_provider", None)

    if llm_provider:
        prompt = build_generation_prompt(
            question=question,
            tier=tier,
            context_text=context_text,
            metrics=metrics,
            previous_error=previous_error,
        )
        try:
            response = call_llm(prompt, config)
            if response:
                return GenerationResult(
                    sql=response.strip(),
                    prompt_used=prompt,
                    from_template=False,
                )
            logger.debug("call_llm returned None, falling back to template")
        except Exception:
            logger.warning("LLM SQL generation failed, falling back to template", exc_info=True)

    # Fallback: offline template
    return generate_sql_template(question, tier, context_text)


def generate_sql_template(
    question: str,
    tier: str,
    context_text: str,
) -> GenerationResult:
    """Generate SQL from offline templates for tiers 1-2 (lookup, aggregation).

    Template coverage:
      LOOKUP:      SELECT TOP 100 * FROM [{table}]
      AGGREGATION: SELECT [{group_col}], COUNT(*) ... FROM [{table}] GROUP BY [{group_col}]
      Others:      Returns sql=None — requires LLM or Analyst Agent

    Table name is extracted from the first "Table: {name}" line in context_text.

    Args:
        question: The natural language question.
        tier: The query tier string.
        context_text: Schema context from assemble_context().

    Returns:
        GenerationResult with from_template=True. sql may be None for complex tiers.
    """
    table_name = _extract_first_table(context_text)

    if tier == "lookup":
        if table_name:
            sql = f"SELECT TOP 100 * FROM [{table_name}]"
        else:
            sql = "SELECT TOP 100 * FROM [<table>]"
        return GenerationResult(sql=sql, prompt_used="", from_template=True)

    if tier == "aggregation":
        sql = _build_aggregation_template(question, table_name)
        return GenerationResult(sql=sql, prompt_used="", from_template=True)

    # Tiers 3-6 (temporal, statistical, forensic, data_quality) require LLM
    return GenerationResult(sql=None, prompt_used="", from_template=True)


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

def _extract_first_table(context_text: str) -> str | None:
    """Extract the first table name from context_text using 'Table: {name}' pattern."""
    match = re.search(r"^Table:\s*(\S+)", context_text, re.MULTILINE)
    if match:
        return match.group(1)
    return None


def _build_aggregation_template(question: str, table_name: str | None) -> str:
    """Build an aggregation SQL template from the question.

    Detects aggregate function keyword (count/sum/avg) and optional
    "by {column}" grouping pattern.
    """
    lower_q = question.lower()
    table = table_name or "<table>"

    # Detect aggregation type
    if "sum" in lower_q:
        agg_func = "SUM"
        agg_col = "amount"  # default column name; actual column unknown without LLM
    elif "avg" in lower_q or "average" in lower_q:
        agg_func = "AVG"
        agg_col = "value"
    else:
        agg_func = "COUNT"
        agg_col = "*"

    # Detect GROUP BY column from "by {word}" pattern
    by_match = re.search(r"\bby\s+(\w+)", lower_q)
    group_col = by_match.group(1) if by_match else None

    if group_col:
        if agg_func == "COUNT":
            return (
                f"SELECT [{group_col}], COUNT(*) AS cnt\n"
                f"FROM [{table}]\n"
                f"GROUP BY [{group_col}]"
            )
        else:
            return (
                f"SELECT [{group_col}], {agg_func}([{agg_col}]) AS result\n"
                f"FROM [{table}]\n"
                f"GROUP BY [{group_col}]"
            )
    else:
        if agg_func == "COUNT":
            return f"SELECT COUNT(*) AS cnt FROM [{table}]"
        else:
            return f"SELECT {agg_func}([{agg_col}]) AS result FROM [{table}]"
