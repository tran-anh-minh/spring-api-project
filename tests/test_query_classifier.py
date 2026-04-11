"""Tests for query tier classifier.

Tests for:
  - classify_query: keyword-based offline classification (6 tiers)
  - classify_query: LLM path with mocked call_llm
  - classify_query: fallback to keyword when LLM returns None
"""
from unittest.mock import patch

import pytest

from db_wiki.core.config import DBWikiConfig, LearningConfig
from db_wiki.query.classifier import QueryTier, classify_query


# -- Keyword classification tests -------------------------------------------

def test_classify_lookup():
    assert classify_query("show me all orders") == QueryTier.LOOKUP


def test_classify_aggregation():
    assert classify_query("count orders by customer") == QueryTier.AGGREGATION


def test_classify_temporal():
    assert classify_query("orders from last month") == QueryTier.TEMPORAL


def test_classify_statistical():
    assert classify_query("average order value by region") == QueryTier.STATISTICAL


def test_classify_forensic():
    assert classify_query("trace where customer data flows") == QueryTier.FORENSIC


def test_classify_data_quality():
    assert classify_query("find columns with NULL values") == QueryTier.DATA_QUALITY


def test_classify_default_lookup_on_no_match():
    """Unrecognized questions default to LOOKUP."""
    assert classify_query("something completely unrecognizable xyz123") == QueryTier.LOOKUP


# -- LLM path tests ----------------------------------------------------------

def _make_config_with_llm():
    """Return config with LLM provider set."""
    return DBWikiConfig(
        learning=LearningConfig(
            llm_provider="claude",
            llm_api_key="test-key",
            llm_model="claude-test",
        )
    )


def test_classify_with_llm_calls_call_llm():
    """When LLM is configured, classify_query calls call_llm and uses the result."""
    config = _make_config_with_llm()
    with patch("db_wiki.query.classifier.call_llm", return_value="aggregation") as mock_llm:
        result = classify_query("count orders by customer", config)
    mock_llm.assert_called_once()
    assert result == QueryTier.AGGREGATION


def test_classify_with_llm_parses_tier_from_response():
    """LLM response containing a valid tier name is correctly parsed."""
    config = _make_config_with_llm()
    with patch("db_wiki.query.classifier.call_llm", return_value="The tier is: temporal"):
        result = classify_query("what happened last week", config)
    assert result == QueryTier.TEMPORAL


def test_classify_with_llm_falls_back_on_none():
    """When LLM returns None, keyword heuristic is used as fallback."""
    config = _make_config_with_llm()
    with patch("db_wiki.query.classifier.call_llm", return_value=None):
        result = classify_query("count orders by customer", config)
    assert result == QueryTier.AGGREGATION


def test_classify_no_llm_config_uses_keywords():
    """Without LLM config, keyword heuristic is used directly."""
    config = DBWikiConfig()  # no LLM
    result = classify_query("trace where customer data flows", config)
    assert result == QueryTier.FORENSIC


def test_classify_with_llm_falls_back_on_unrecognised_response():
    """When LLM returns an unrecognized tier string, fall back to keyword heuristic."""
    config = _make_config_with_llm()
    with patch("db_wiki.query.classifier.call_llm", return_value="unknown_tier_xyz"):
        result = classify_query("count orders by customer", config)
    assert result == QueryTier.AGGREGATION


# -- QueryTier enum values ---------------------------------------------------

def test_query_tier_values():
    """QueryTier has all 6 expected values."""
    assert QueryTier.LOOKUP == "lookup"
    assert QueryTier.AGGREGATION == "aggregation"
    assert QueryTier.TEMPORAL == "temporal"
    assert QueryTier.STATISTICAL == "statistical"
    assert QueryTier.FORENSIC == "forensic"
    assert QueryTier.DATA_QUALITY == "data_quality"
