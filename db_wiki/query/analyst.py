"""Analyst Agent for Tier 3+ query decomposition.

Decomposes complex NL questions into simpler sub-questions that can each be
answered by a single SQL query. Composes results into a unified CTE-based query.

Used by QueryPipeline for tier 3+ queries (TEMPORAL, STATISTICAL, FORENSIC,
DATA_QUALITY) when an LLM is configured. Falls back to single-pass pipeline
when no LLM is available.

Security note (T-04-09): LLM decomposition could produce misleading sub-questions,
but each sub-query goes through the full validation pipeline. Worst case: bad SQL
caught by validator, retried, or returned as None.
"""
from __future__ import annotations

import logging
import re

from db_wiki.learning.agents.base import call_llm

logger = logging.getLogger(__name__)

# Prompt for decomposing complex questions into sub-questions
_DECOMPOSE_PROMPT = """\
Break this complex database question into simpler sub-questions that can each be answered with a single SQL query.

Question: {question}
Tier: {tier}

Return one sub-question per line, numbered (e.g., "1. ...", "2. ...").
Each sub-question should be self-contained and answerable with a single SELECT statement.
"""

# Prompt for composing sub-query results into a unified CTE query
_COMPOSE_PROMPT = """\
Combine these sub-query SQL statements into a single T-SQL CTE-based query that answers the original question.

Original question: {question}

Sub-queries:
{sub_queries}

Requirements:
- Use WITH ... AS CTEs for each sub-query
- Produce a single final SELECT that joins or unions the CTEs
- Use T-SQL syntax (TOP N, GETDATE(), square bracket quoting)
- Return ONLY the SQL, no explanation.
"""


class AnalystAgent:
    """Analyst Agent for decomposing and composing Tier 3+ queries.

    Follows the agent pattern from learning/agents/base.py but does not
    extend the base class — this is a query-time agent, not a learning agent.
    """

    def __init__(self, config) -> None:
        """Initialise with DBWikiConfig.

        Args:
            config: DBWikiConfig instance.
        """
        self._config = config

    def decompose(self, question: str, tier: str) -> list[str]:
        """Decompose a complex question into simpler sub-questions.

        If an LLM is configured, sends a structured decomposition prompt and
        parses the numbered response into a list of sub-question strings.

        Falls back to [question] (single-pass) if:
          - LLM is not configured
          - call_llm returns None
          - LLM response cannot be parsed into sub-questions

        Args:
            question: The complex NL question to decompose.
            tier: The query tier string (e.g. "temporal", "statistical").

        Returns:
            List of sub-question strings. Minimum: [question] (single-pass fallback).
        """
        llm_provider = getattr(
            getattr(self._config, "learning", None), "llm_provider", None
        )
        if not llm_provider:
            return [question]

        prompt = _DECOMPOSE_PROMPT.format(question=question, tier=tier)
        try:
            response = call_llm(prompt, self._config)
        except Exception:
            logger.warning("AnalystAgent.decompose LLM call failed", exc_info=True)
            return [question]

        if not response:
            return [question]

        sub_questions = _parse_numbered_list(response)
        if not sub_questions:
            logger.debug("AnalystAgent.decompose: could not parse LLM response into sub-questions")
            return [question]

        return sub_questions

    def compose(self, sub_results: list, original_question: str) -> str | None:
        """Compose sub-query results into a unified CTE-based SQL query.

        If an LLM is configured, builds a composition prompt from successful
        sub-query SQLs and returns the LLM response.

        Falls back to returning the sql from the first sub_result that has a
        non-None sql when LLM is not configured or fails.

        Args:
            sub_results: List of QueryResult objects (or dicts with 'sql' key).
            original_question: The original NL question being answered.

        Returns:
            A combined SQL string, or None if no sub-result has valid SQL.
        """
        # Collect successful sub-query SQLs
        successful_sqls = []
        for i, result in enumerate(sub_results):
            sql = result.sql if hasattr(result, "sql") else result.get("sql")
            if sql is not None:
                successful_sqls.append((i + 1, sql))

        if not successful_sqls:
            return None

        llm_provider = getattr(
            getattr(self._config, "learning", None), "llm_provider", None
        )
        if not llm_provider:
            # Offline fallback: return first successful sub-result's SQL
            return successful_sqls[0][1]

        sub_queries_text = "\n\n".join(
            f"Sub-query {i}:\n{sql}" for i, sql in successful_sqls
        )
        prompt = _COMPOSE_PROMPT.format(
            question=original_question,
            sub_queries=sub_queries_text,
        )

        try:
            response = call_llm(prompt, self._config)
        except Exception:
            logger.warning("AnalystAgent.compose LLM call failed", exc_info=True)
            return successful_sqls[0][1]

        if not response:
            return successful_sqls[0][1]

        return response.strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_numbered_list(text: str) -> list[str]:
    """Parse a numbered list from LLM output into a list of strings.

    Handles formats like "1. question text", "1) question text", "1: question text".
    Also falls back to non-empty lines when no numbered format is detected.

    Args:
        text: The LLM response text.

    Returns:
        List of extracted item strings, or empty list if parsing fails.
    """
    lines = text.strip().splitlines()
    items: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Match numbered patterns: "1.", "1)", "1:"
        match = re.match(r"^\d+[.):\s]+\s*(.+)", line)
        if match:
            items.append(match.group(1).strip())

    # If no numbered items found, treat each non-empty line as a sub-question
    if not items:
        items = [line.strip() for line in lines if line.strip()]

    return items
