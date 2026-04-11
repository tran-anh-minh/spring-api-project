"""Tests for db_wiki/query/analyst.py — Analyst Agent (AGENT-03 requirement).

Dedicated tests covering:
  - AnalystAgent.decompose() with LLM and without LLM (offline fallback)
  - AnalystAgent.compose() with LLM and without LLM (offline fallback)
"""
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from db_wiki.core.config import DBWikiConfig
from db_wiki.query.analyst import AnalystAgent, _parse_numbered_list


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_config_with_llm():
    """DBWikiConfig with LLM provider configured (mocked — no real API calls)."""
    cfg = DBWikiConfig()
    cfg.learning.llm_provider = "claude"
    cfg.learning.llm_api_key = "test-key"
    return cfg


def _make_config_no_llm():
    """DBWikiConfig with no LLM provider (offline mode)."""
    return DBWikiConfig()


@dataclass
class FakeQueryResult:
    """Minimal stand-in for QueryResult used in compose() tests."""
    sql: str | None


# ---------------------------------------------------------------------------
# _parse_numbered_list helper
# ---------------------------------------------------------------------------


def test_parse_numbered_list_dot_format():
    text = "1. Find all orders\n2. Find customers with missing emails\n3. Join the results"
    items = _parse_numbered_list(text)
    assert len(items) == 3
    assert items[0] == "Find all orders"
    assert items[1] == "Find customers with missing emails"
    assert items[2] == "Join the results"


def test_parse_numbered_list_paren_format():
    text = "1) First sub-question\n2) Second sub-question"
    items = _parse_numbered_list(text)
    assert len(items) == 2
    assert items[0] == "First sub-question"


def test_parse_numbered_list_colon_format():
    text = "1: Find orders\n2: Find emails"
    items = _parse_numbered_list(text)
    assert len(items) == 2


def test_parse_numbered_list_fallback_no_numbers():
    text = "Find all orders\nFind customers with missing emails"
    items = _parse_numbered_list(text)
    assert len(items) == 2
    assert items[0] == "Find all orders"


def test_parse_numbered_list_empty_returns_empty():
    assert _parse_numbered_list("") == []
    assert _parse_numbered_list("   ") == []


# ---------------------------------------------------------------------------
# AnalystAgent.decompose()
# ---------------------------------------------------------------------------


class TestDecompose:
    def test_decompose_with_llm_parses_numbered_list(self):
        """LLM response with numbered sub-questions is parsed correctly."""
        cfg = _make_config_with_llm()
        agent = AnalystAgent(cfg)

        llm_response = "1. Find orders from last month\n2. Find customers with missing emails\n3. Join orders to customers"

        with patch("db_wiki.query.analyst.call_llm", return_value=llm_response):
            result = agent.decompose("find orders with missing emails from last month", "temporal")

        assert len(result) >= 2
        assert all(isinstance(q, str) for q in result)
        assert "Find orders from last month" in result

    def test_decompose_without_llm_returns_original_question(self):
        """No LLM configured — decompose() returns [original_question] (offline fallback)."""
        cfg = _make_config_no_llm()
        agent = AnalystAgent(cfg)

        question = "find orders with missing emails from last month"
        result = agent.decompose(question, "temporal")

        assert result == [question]

    def test_decompose_llm_returns_none_falls_back_to_original(self):
        """LLM returns None — decompose() falls back to [original_question]."""
        cfg = _make_config_with_llm()
        agent = AnalystAgent(cfg)
        question = "some complex question"

        with patch("db_wiki.query.analyst.call_llm", return_value=None):
            result = agent.decompose(question, "statistical")

        assert result == [question]

    def test_decompose_llm_exception_falls_back_to_original(self):
        """LLM raises exception — decompose() falls back to [original_question]."""
        cfg = _make_config_with_llm()
        agent = AnalystAgent(cfg)
        question = "complex question"

        with patch("db_wiki.query.analyst.call_llm", side_effect=RuntimeError("network error")):
            result = agent.decompose(question, "forensic")

        assert result == [question]

    def test_decompose_with_llm_passes_question_and_tier_in_prompt(self):
        """Verify the LLM prompt contains the question and tier."""
        cfg = _make_config_with_llm()
        agent = AnalystAgent(cfg)
        question = "find top customers by revenue"

        captured_prompts = []

        def capture_prompt(prompt, config):
            captured_prompts.append(prompt)
            return "1. Find revenue per customer\n2. Rank by revenue"

        with patch("db_wiki.query.analyst.call_llm", side_effect=capture_prompt):
            agent.decompose(question, "statistical")

        assert len(captured_prompts) == 1
        assert question in captured_prompts[0]
        assert "statistical" in captured_prompts[0]


# ---------------------------------------------------------------------------
# AnalystAgent.compose()
# ---------------------------------------------------------------------------


class TestCompose:
    def test_compose_with_llm_returns_cte_sql(self):
        """LLM configured — compose() returns LLM response (CTE SQL)."""
        cfg = _make_config_with_llm()
        agent = AnalystAgent(cfg)

        sub_results = [
            FakeQueryResult(sql="SELECT id FROM Orders"),
            FakeQueryResult(sql="SELECT id FROM Customers WHERE email IS NULL"),
        ]

        cte_sql = (
            "WITH orders AS (SELECT id FROM Orders),\n"
            "missing_emails AS (SELECT id FROM Customers WHERE email IS NULL)\n"
            "SELECT o.id FROM orders o JOIN missing_emails m ON o.id = m.id"
        )

        with patch("db_wiki.query.analyst.call_llm", return_value=cte_sql):
            result = agent.compose(sub_results, "find orders with missing emails")

        assert result == cte_sql

    def test_compose_without_llm_returns_first_successful_sql(self):
        """No LLM configured — compose() returns the first non-None sql."""
        cfg = _make_config_no_llm()
        agent = AnalystAgent(cfg)

        sub_results = [
            FakeQueryResult(sql=None),
            FakeQueryResult(sql="SELECT TOP 100 * FROM Orders"),
            FakeQueryResult(sql="SELECT * FROM Customers"),
        ]

        result = agent.compose(sub_results, "original question")

        assert result == "SELECT TOP 100 * FROM Orders"

    def test_compose_all_none_sql_returns_none(self):
        """All sub-results have None sql — compose() returns None."""
        cfg = _make_config_no_llm()
        agent = AnalystAgent(cfg)

        sub_results = [
            FakeQueryResult(sql=None),
            FakeQueryResult(sql=None),
        ]

        result = agent.compose(sub_results, "complex question")
        assert result is None

    def test_compose_empty_sub_results_returns_none(self):
        cfg = _make_config_no_llm()
        agent = AnalystAgent(cfg)

        result = agent.compose([], "original question")
        assert result is None

    def test_compose_llm_returns_none_falls_back_to_first_sql(self):
        """LLM configured but returns None — compose() falls back to first successful sql."""
        cfg = _make_config_with_llm()
        agent = AnalystAgent(cfg)

        sub_results = [
            FakeQueryResult(sql="SELECT 1"),
            FakeQueryResult(sql="SELECT 2"),
        ]

        with patch("db_wiki.query.analyst.call_llm", return_value=None):
            result = agent.compose(sub_results, "some question")

        assert result == "SELECT 1"

    def test_compose_with_llm_passes_original_question_in_prompt(self):
        """Verify original question appears in the compose prompt."""
        cfg = _make_config_with_llm()
        agent = AnalystAgent(cfg)
        original_question = "find missing order emails"

        sub_results = [FakeQueryResult(sql="SELECT id FROM Orders")]
        captured_prompts = []

        def capture(prompt, config):
            captured_prompts.append(prompt)
            return "WITH cte AS (SELECT id FROM Orders) SELECT * FROM cte"

        with patch("db_wiki.query.analyst.call_llm", side_effect=capture):
            agent.compose(sub_results, original_question)

        assert original_question in captured_prompts[0]
