"""Shared agent infrastructure for the learning loop.

Provides:
  - call_llm: optional LLM client (Claude / OpenAI) with offline fallback
  - create_task_record: persist an agent_tasks row (bi-temporal)
  - save_result_record: persist an agent_results row
  - complete_task: transition task status via bi-temporal invalidate+insert
"""

from __future__ import annotations

import json
import logging
import sqlite3

from db_wiki.learning.models import AgentFindings

logger = logging.getLogger(__name__)


def call_llm(prompt: str, config) -> str | None:
    """Call an LLM provider if configured, else return None (offline mode).

    LLM SDKs are imported inside the function body so they remain soft
    dependencies — the learning loop works fully offline without them.
    """
    if not config.learning.llm_provider or not config.learning.llm_api_key:
        return None

    try:
        if config.learning.llm_provider == "claude":
            import anthropic  # noqa: F811

            client = anthropic.Anthropic(api_key=config.learning.llm_api_key)
            msg = client.messages.create(
                model=config.learning.llm_model or "claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text

        if config.learning.llm_provider == "openai":
            import openai  # noqa: F811

            client = openai.OpenAI(api_key=config.learning.llm_api_key)
            resp = client.chat.completions.create(
                model=config.learning.llm_model or "gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            return resp.choices[0].message.content

    except ImportError:
        logger.warning("LLM SDK not installed for provider %s", config.learning.llm_provider)
    except Exception:
        logger.warning("LLM call failed", exc_info=True)

    return None


def create_task_record(
    conn: sqlite3.Connection,
    gap_id: int,
    agent_type: str,
    input_data: dict | None,
    now_ts: int,
    now_iso: str,
) -> int:
    """Insert a new agent_tasks row with status='running'."""
    input_json = json.dumps(input_data) if input_data else None
    cur = conn.execute(
        """INSERT INTO agent_tasks
           (gap_id, agent_type, status, input_json,
            valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, ?, 'running', ?, ?, ?, ?, ?)""",
        (gap_id, agent_type, input_json, now_iso, now_ts, now_iso, now_ts),
    )
    conn.commit()
    return cur.lastrowid


def save_result_record(
    conn: sqlite3.Connection,
    task_id: int,
    agent_type: str,
    findings: AgentFindings,
    approved: bool | None,
    now_ts: int,
    now_iso: str,
) -> int:
    """Insert a new agent_results row."""
    cur = conn.execute(
        """INSERT INTO agent_results
           (task_id, agent_type, success, findings_json, rationale, approved,
            valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            agent_type,
            1 if len(findings.items) > 0 else 0,
            findings.model_dump_json(),
            findings.summary,
            1 if approved is True else (0 if approved is False else None),
            now_iso, now_ts, now_iso, now_ts,
        ),
    )
    conn.commit()
    return cur.lastrowid


def complete_task(
    conn: sqlite3.Connection,
    task_id: int,
    status: str,
    now_ts: int,
    now_iso: str,
) -> None:
    """Transition task status via bi-temporal invalidate + insert."""
    row = conn.execute(
        "SELECT * FROM current_agent_tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if row is None:
        return

    # Invalidate current row
    conn.execute(
        """UPDATE agent_tasks
           SET invalidated_at = ?, invalidated_at_ts = ?
           WHERE id = ? AND invalidated_at IS NULL""",
        (now_iso, now_ts, task_id),
    )

    # Insert new version with updated status
    conn.execute(
        """INSERT INTO agent_tasks
           (gap_id, agent_type, status, input_json,
            valid_from, valid_from_ts, recorded_at, recorded_at_ts)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (row["gap_id"], row["agent_type"], status, row["input_json"],
         now_iso, now_ts, now_iso, now_ts),
    )
    conn.commit()
