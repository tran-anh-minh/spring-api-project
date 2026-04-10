"""
Wave 0 test stubs for gap detection requirements.

Covers:
  LEARN-01: detect_all_gaps is the entry point of the Discover phase
  LEARN-02: 12 gap detection rules
  LEARN-03: priority scoring with configurable weights and cooldown-aware selection
  LEARN-11 (partial): gap dedup prevents infinite cycling
"""
import pytest
import sqlite3


@pytest.mark.xfail(reason="Wave 0 stub - awaiting Plan 02 implementation")
class TestGapDetection:
    def test_detect_all_gaps_returns_gap_list(self):
        from db_wiki.learning.gap_detector import detect_all_gaps
        # LEARN-01: detect_all_gaps is the entry point of the Discover phase
        conn = sqlite3.connect(":memory:")
        result = detect_all_gaps(conn, 0, "2026-01-01T00:00:00")
        assert isinstance(result, list)

    def test_twelve_detection_rules_exist(self):
        from db_wiki.learning import gap_detector
        # LEARN-02: 12 gap detection rules
        rules = [name for name in dir(gap_detector) if name.startswith("detect_")]
        assert len(rules) >= 12

    def test_upsert_gaps_deduplicates(self):
        from db_wiki.learning.gap_detector import upsert_gaps
        # LEARN-11 (partial): gap dedup prevents infinite cycling

    def test_gap_scoring_formula(self):
        from db_wiki.learning.gap_scorer import score_gap
        # LEARN-03: priority scoring with configurable weights

    def test_eligible_gaps_respects_cooldown(self):
        from db_wiki.learning.gap_scorer import get_eligible_gaps
        # LEARN-03: cooldown-aware gap selection
