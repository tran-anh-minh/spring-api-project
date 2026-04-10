"""
Wave 0 test stubs for agent requirements.

Covers:
  AGENT-01: Research Agent works without LLM (heuristic mode)
  AGENT-02: Review Agent quality gate
  AGENT-04: Collector Agent falls back when no DB connection
  AGENT-05: Orchestrator full loop coordination and handles empty store
"""
import pytest


@pytest.mark.xfail(reason="Wave 0 stub - awaiting Plan 04/05 implementation")
class TestAgents:
    def test_collector_no_db_returns_empty(self):
        from db_wiki.learning.agents.collector import collect_evidence
        # AGENT-04: Collector falls back when no DB connection

    def test_research_heuristic_mode(self):
        from db_wiki.learning.agents.research import research_gap
        # AGENT-01: Research works without LLM

    def test_review_rejects_low_quality(self):
        from db_wiki.learning.agents.review import review_findings
        # AGENT-02: Review quality gate

    def test_orchestrator_full_cycle(self):
        from db_wiki.learning.orchestrator import run_learning_loop
        # AGENT-05: Full loop coordination

    def test_orchestrator_empty_store(self):
        from db_wiki.learning.orchestrator import run_learning_loop
        # AGENT-05: Handles empty store gracefully
