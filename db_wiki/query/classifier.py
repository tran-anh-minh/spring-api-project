"""Query tier classifier for the NL-to-SQL pipeline.

Classifies natural language questions into one of 6 tiers:
  LOOKUP, AGGREGATION, TEMPORAL, STATISTICAL, FORENSIC, DATA_QUALITY

Classification uses keyword heuristics offline, with optional LLM enhancement
when a provider is configured (config.learning.llm_provider is not None).

Security note (T-04-03): User question is embedded in LLM prompt as plain text.
LLM output is only used for tier classification (selecting from a known enum) —
never executed as SQL.
"""
from __future__ import annotations

import logging
from enum import Enum

from db_wiki.learning.agents.base import call_llm

logger = logging.getLogger(__name__)


class QueryTier(str, Enum):
    """Six-tier classification for NL questions based on query complexity."""

    LOOKUP = "lookup"
    AGGREGATION = "aggregation"
    TEMPORAL = "temporal"
    STATISTICAL = "statistical"
    FORENSIC = "forensic"
    DATA_QUALITY = "data_quality"


# Keyword maps for offline heuristic classification.
# Each tier has a list of trigger words/phrases (checked on lowercased question).
TIER_KEYWORDS: dict[QueryTier, list[str]] = {
    QueryTier.LOOKUP: [
        "show", "find", "get", "list", "what is", "which", "select", "display",
    ],
    QueryTier.AGGREGATION: [
        "count", "total", "sum", "how many", "group by", "per", "breakdown",
    ],
    QueryTier.TEMPORAL: [
        "last month", "last week", "yesterday", "date range", "between",
        "since", "before", "after", "when", "trend", "over time",
    ],
    QueryTier.STATISTICAL: [
        "average", "mean", "median", "percentage", "ratio", "distribution",
        "top", "bottom", "rank", "compare",
    ],
    QueryTier.FORENSIC: [
        "trace", "flow", "where does", "lineage", "source", "feeds",
        "upstream", "downstream", "path",
    ],
    QueryTier.DATA_QUALITY: [
        "null", "missing", "invalid", "duplicate", "orphan", "inconsistent",
        "quality", "empty", "stale",
    ],
}

# Tier names for LLM response parsing (canonical lower-case values)
_TIER_NAMES = {t.value: t for t in QueryTier}

# LLM classification prompt template
_CLASSIFICATION_PROMPT = """\
You are classifying a database question into one of the following tiers:
  lookup, aggregation, temporal, statistical, forensic, data_quality

Definitions:
  lookup      - simple row retrieval, no aggregation, no time filter
  aggregation - COUNT, SUM, GROUP BY style queries
  temporal    - time-based filtering or trend analysis
  statistical - averages, distributions, rankings, percentages
  forensic    - data lineage tracing, flow analysis, upstream/downstream
  data_quality - NULL detection, duplicate checks, data validation

Respond with ONLY the tier name (one word, lowercase).

Question: {question}
"""


def _keyword_classify(question: str) -> QueryTier:
    """Classify using keyword heuristics on the lowercased question.

    Counts keyword matches per tier; returns tier with most matches.
    More-specific tiers (defined later in the enum) win on equal score,
    preventing generic terms like "find" (LOOKUP) from overriding specific
    signals like "null" (DATA_QUALITY).
    Defaults to LOOKUP if no keywords match.
    """
    lower = question.lower()
    scores: dict[QueryTier, int] = {tier: 0 for tier in QueryTier}

    for tier, keywords in TIER_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                scores[tier] += 1

    best_tier = QueryTier.LOOKUP
    best_score = 0
    for tier in QueryTier:  # iterate in definition order
        # Use >= so that more-specific tiers (defined later) win ties over
        # generic ones (e.g., DATA_QUALITY beats LOOKUP on equal score)
        if scores[tier] >= best_score and scores[tier] > 0:
            best_score = scores[tier]
            best_tier = tier

    return best_tier


def _parse_llm_tier(response: str) -> QueryTier | None:
    """Extract a QueryTier from an LLM response string.

    Searches for any known tier value in the response (case-insensitive).
    Returns None if no tier is found.
    """
    if not response:
        return None
    lower = response.lower()
    for name, tier in _TIER_NAMES.items():
        if name in lower:
            return tier
    return None


def classify_query(question: str, config=None) -> QueryTier:
    """Classify a natural language question into a QueryTier.

    If *config* has an LLM provider configured (config.learning.llm_provider
    is not None), attempts LLM classification first. Falls back to keyword
    heuristics on LLM failure, None response, or unrecognized output.

    Args:
        question: The natural language question to classify.
        config: DBWikiConfig instance, or None to use keyword-only mode.

    Returns:
        The QueryTier that best matches the question.
    """
    # Try LLM classification if provider is configured
    if config is not None and getattr(getattr(config, "learning", None), "llm_provider", None):
        prompt = _CLASSIFICATION_PROMPT.format(question=question)
        try:
            response = call_llm(prompt, config)
            if response:
                tier = _parse_llm_tier(response)
                if tier is not None:
                    return tier
                logger.debug("LLM returned unrecognized tier '%s', falling back to keywords", response)
        except Exception:
            logger.warning("LLM classification failed, falling back to keywords", exc_info=True)

    return _keyword_classify(question)
