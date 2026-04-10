"""Learning loop orchestrator — coordinates the five-phase learning cycle.

Phases:
  1. Discover: detect_all_gaps + upsert_gaps
  2. Prioritize: score_and_prioritize + get_eligible_gaps
  3. Investigate: Collector gathers evidence
  4. Reason + Validate: Research analyzes, Review approves/rejects
  5. Consolidate: apply_findings or bump_attempt_count

Entry point: run_learning_loop(conn, config) -> summary string.
Manual trigger only — scheduling deferred to Phase 5 (D-06).
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone

from db_wiki.core.config import DBWikiConfig
from db_wiki.learning.agents.base import (
    complete_task,
    create_task_record,
    save_result_record,
)
from db_wiki.learning.agents.collector import collect_evidence
from db_wiki.learning.agents.research import research_gap
from db_wiki.learning.agents.review import review_findings
from db_wiki.learning.gap_detector import detect_all_gaps, upsert_gaps
from db_wiki.learning.gap_scorer import get_eligible_gaps, score_and_prioritize
from db_wiki.learning.pipeline import apply_findings, bump_attempt_count, mark_gap_resolved

logger = logging.getLogger(__name__)


def run_learning_loop(conn: sqlite3.Connection, config: DBWikiConfig) -> str:
    """Execute one full learning cycle.

    Processes up to config.learning.max_gaps_per_run gaps in a single pass.
    Each gap is processed independently — a failure in one does not abort others.

    Args:
        conn: SQLite knowledge store connection (row_factory = sqlite3.Row).
        config: Full application config.

    Returns:
        Summary string with discovered/processed/approved counts.
    """
    now_ts = int(time.time())
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    logger.info("Learning loop started")

    # ── Phase 1: Discover ────────────────────────────────────────
    new_gaps = detect_all_gaps(conn, now_ts, now_iso)
    gap_ids = upsert_gaps(conn, new_gaps, now_ts, now_iso)
    conn.commit()
    tracked = len([g for g in gap_ids if g is not None])
    logger.info("Discover: %d gaps detected, %d new tracked", len(new_gaps), tracked)

    # ── Phase 2: Prioritize and select ───────────────────────────
    score_and_prioritize(conn, config.learning)
    conn.commit()
    batch = get_eligible_gaps(conn, config.learning.max_gaps_per_run, now_ts)
    logger.info("Selected %d gaps for processing", len(batch))

    # ── Phases 3-5: Process each gap ─────────────────────────────
    approved_count = 0
    processed_count = 0

    for gap in batch:
        try:
            processed_count += 1

            # Investigate: Collector gathers evidence
            task_id = create_task_record(
                conn, gap.id, "collector",
                {"gap_type": gap.gap_type, "entity_name": gap.entity_name},
                now_ts, now_iso,
            )
            evidence = collect_evidence(conn, gap, config)
            save_result_record(conn, task_id, "collector", evidence, None, now_ts, now_iso)
            complete_task(conn, task_id, "done", now_ts, now_iso)

            # Reason: Research Agent analyzes
            task_id = create_task_record(conn, gap.id, "research", None, now_ts, now_iso)
            findings = research_gap(conn, gap, evidence, config)
            save_result_record(conn, task_id, "research", findings, None, now_ts, now_iso)
            complete_task(conn, task_id, "done", now_ts, now_iso)

            # Validate: Review Agent approves/rejects
            task_id = create_task_record(conn, gap.id, "review", None, now_ts, now_iso)
            reviewed = review_findings(conn, gap, findings, config)
            has_approved = len(reviewed.items) > 0
            save_result_record(conn, task_id, "review", reviewed, has_approved, now_ts, now_iso)
            complete_task(conn, task_id, "done", now_ts, now_iso)

            # Consolidate: Apply or bump
            if has_approved:
                results = apply_findings(conn, gap, reviewed, now_ts, now_iso)
                mark_gap_resolved(conn, gap.id, now_ts, now_iso)
                approved_count += 1
                logger.info("Gap %d (%s): resolved. %s", gap.id, gap.gap_type, results)
            else:
                bump_attempt_count(
                    conn, gap.id,
                    config.learning.cooldown_hours,
                    config.learning.max_attempts_before_permanent,
                    now_ts, now_iso,
                )
                logger.info("Gap %d (%s): rejected, attempt bumped", gap.id, gap.gap_type)

            conn.commit()

        except Exception:
            logger.error("Error processing gap %d", gap.id, exc_info=True)
            conn.rollback()
            try:
                bump_attempt_count(
                    conn, gap.id,
                    config.learning.cooldown_hours,
                    config.learning.max_attempts_before_permanent,
                    now_ts, now_iso,
                )
                conn.commit()
            except Exception:
                pass

    summary = f"Discovered {len(new_gaps)} gaps, processed {processed_count}, approved {approved_count}"
    logger.info("Learning loop complete: %s", summary)
    return summary
