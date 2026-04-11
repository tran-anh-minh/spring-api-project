"""Tests for SQL generator.

Tests for:
  - build_generation_prompt: prompt construction with context, metrics, retry error
  - generate_sql: LLM path calls call_llm with built prompt
  - generate_sql: falls back to template when LLM not configured or returns None
  - generate_sql_template: offline template for lookup and aggregation tiers
"""
from unittest.mock import patch

import pytest

from db_wiki.core.config import DBWikiConfig, LearningConfig
from db_wiki.query.generator import (
    GenerationResult,
    build_generation_prompt,
    generate_sql,
    generate_sql_template,
)


# -- build_generation_prompt -------------------------------------------------

def test_prompt_contains_context():
    prompt = build_generation_prompt(
        question="show all orders",
        tier="lookup",
        context_text="Table: Orders\n  Columns: OrderID INT [PK]",
    )
    assert "Table: Orders" in prompt
    assert "== Schema Context ==" in prompt


def test_prompt_contains_question_and_tier():
    prompt = build_generation_prompt(
        question="show all orders",
        tier="lookup",
        context_text="some context",
    )
    assert "show all orders" in prompt
    assert "lookup" in prompt


def test_prompt_contains_metrics_when_provided():
    metrics = [{"name": "revenue", "formula": "SUM(amount)"}]
    prompt = build_generation_prompt(
        question="total revenue",
        tier="aggregation",
        context_text="ctx",
        metrics=metrics,
    )
    assert "Defined Metrics" in prompt
    assert "revenue" in prompt


def test_prompt_no_metrics_section_when_none():
    prompt = build_generation_prompt(
        question="show all orders",
        tier="lookup",
        context_text="ctx",
        metrics=None,
    )
    assert "Defined Metrics" not in prompt


def test_prompt_contains_previous_error_on_retry():
    prompt = build_generation_prompt(
        question="show all orders",
        tier="lookup",
        context_text="ctx",
        previous_error="Unknown column: xyz",
    )
    assert "Previous attempt failed" in prompt
    assert "Unknown column: xyz" in prompt


def test_prompt_ends_with_generate_tsql():
    prompt = build_generation_prompt(
        question="show all orders",
        tier="lookup",
        context_text="ctx",
    )
    assert "T-SQL" in prompt or "tsql" in prompt.lower() or "T-SQL only" in prompt


# -- generate_sql (LLM path) -------------------------------------------------

def _config_with_llm():
    return DBWikiConfig(
        learning=LearningConfig(
            llm_provider="claude",
            llm_api_key="test-key",
            llm_model="claude-test",
        )
    )


def test_generate_sql_calls_call_llm_when_configured():
    config = _config_with_llm()
    with patch("db_wiki.query.generator.call_llm", return_value="SELECT TOP 100 * FROM [Orders]") as mock_llm:
        result = generate_sql(
            question="show all orders",
            tier="lookup",
            context_text="Table: Orders",
            config=config,
        )
    mock_llm.assert_called_once()
    assert result.sql == "SELECT TOP 100 * FROM [Orders]"
    assert result.from_template is False


def test_generate_sql_prompt_contains_context_and_tier():
    config = _config_with_llm()
    captured_prompt = {}

    def capture_llm(prompt, cfg):
        captured_prompt["value"] = prompt
        return "SELECT * FROM t"

    with patch("db_wiki.query.generator.call_llm", side_effect=capture_llm):
        generate_sql(
            question="count orders by status",
            tier="aggregation",
            context_text="Table: Orders",
            config=config,
        )

    assert "count orders by status" in captured_prompt["value"]
    assert "aggregation" in captured_prompt["value"]
    assert "Table: Orders" in captured_prompt["value"]


def test_generate_sql_includes_previous_error_in_prompt():
    config = _config_with_llm()
    captured_prompt = {}

    def capture_llm(prompt, cfg):
        captured_prompt["value"] = prompt
        return "SELECT * FROM t"

    with patch("db_wiki.query.generator.call_llm", side_effect=capture_llm):
        generate_sql(
            question="show all orders",
            tier="lookup",
            context_text="ctx",
            config=config,
            previous_error="Unknown column: badcol",
        )

    assert "Previous attempt failed" in captured_prompt["value"]
    assert "Unknown column: badcol" in captured_prompt["value"]


def test_generate_sql_includes_metrics_in_prompt():
    config = _config_with_llm()
    captured_prompt = {}

    def capture_llm(prompt, cfg):
        captured_prompt["value"] = prompt
        return "SELECT SUM(amount) FROM Orders"

    metrics = [{"name": "revenue", "formula": "SUM(amount)"}]
    with patch("db_wiki.query.generator.call_llm", side_effect=capture_llm):
        generate_sql(
            question="total revenue",
            tier="aggregation",
            context_text="ctx",
            config=config,
            metrics=metrics,
        )

    assert "Defined Metrics" in captured_prompt["value"]
    assert "revenue" in captured_prompt["value"]


def test_generate_sql_falls_back_to_template_when_no_llm():
    config = DBWikiConfig()  # no LLM
    result = generate_sql(
        question="show all orders",
        tier="lookup",
        context_text="Table: Orders\n  Columns: OrderID INT [PK], Status NVARCHAR",
        config=config,
    )
    assert result.from_template is True


def test_generate_sql_falls_back_to_template_when_llm_returns_none():
    config = _config_with_llm()
    with patch("db_wiki.query.generator.call_llm", return_value=None):
        result = generate_sql(
            question="show all orders",
            tier="lookup",
            context_text="Table: Orders\n  Columns: OrderID INT [PK]",
            config=config,
        )
    assert result.from_template is True


# -- generate_sql_template ---------------------------------------------------

def test_template_lookup_returns_select_top():
    result = generate_sql_template(
        question="show all orders",
        tier="lookup",
        context_text="Table: Orders\n  Columns: OrderID INT [PK], CustomerID INT",
    )
    assert result.from_template is True
    assert result.sql is not None
    assert "SELECT TOP 100" in result.sql
    assert "Orders" in result.sql


def test_template_aggregation_returns_count_group_by():
    result = generate_sql_template(
        question="count orders by status",
        tier="aggregation",
        context_text="Table: Orders\n  Columns: OrderID INT [PK], Status NVARCHAR",
    )
    assert result.from_template is True
    assert result.sql is not None
    assert "COUNT" in result.sql
    assert "GROUP BY" in result.sql


def test_template_forensic_returns_none_sql():
    """Complex tiers return sql=None from template (requires LLM or Analyst Agent)."""
    result = generate_sql_template(
        question="trace where customer data flows",
        tier="forensic",
        context_text="ctx",
    )
    assert result.from_template is True
    assert result.sql is None


def test_template_temporal_returns_none_sql():
    result = generate_sql_template(
        question="orders from last month",
        tier="temporal",
        context_text="ctx",
    )
    assert result.from_template is True
    assert result.sql is None


# -- GenerationResult dataclass ----------------------------------------------

def test_generation_result_has_required_fields():
    r = GenerationResult(sql="SELECT 1", prompt_used="p", from_template=False)
    assert r.sql == "SELECT 1"
    assert r.prompt_used == "p"
    assert r.from_template is False
