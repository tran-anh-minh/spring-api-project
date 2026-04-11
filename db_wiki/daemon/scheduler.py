"""Background learning loop scheduler (LEARN-13, D-04, D-05).

Uses schedule library (instance-level, not global) to run learning loop
at fast/medium/deep intervals. Each scheduler thread opens its own
SQLite connection for thread safety (RESEARCH pitfall 1).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

import schedule

logger = logging.getLogger(__name__)

# Default fast interval bounds for adaptive frequency
_FAST_MIN_MINUTES = 1
_FAST_MAX_MINUTES = 30


class DaemonScheduler:
    """Background scheduler for the learning loop.

    Thread safety: opens its own SQLite connection via open_store(db_path)
    in the scheduler thread (not sharing the main thread's connection).
    Uses schedule.Scheduler() instance (not global schedule module) to
    prevent job accumulation across multiple starts (RESEARCH pitfall 4).

    Args:
        db_path: Path to the SQLite knowledge store. Optional for testing.
        config: Full application config. Optional for testing.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        config=None,
    ):
        self._db_path = db_path
        self._config = config
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._scheduler = schedule.Scheduler()  # instance-level, not global
        self._run_count = 0
        self._last_gap_count: Optional[int] = None

    def start(self) -> None:
        """Start the background scheduler thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Scheduler already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="db-wiki-scheduler"
        )
        self._thread.start()
        logger.info("Daemon scheduler started")

    def stop(self) -> None:
        """Signal the scheduler to stop."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        logger.info("Daemon scheduler stopped")

    @property
    def is_running(self) -> bool:
        """True if the scheduler thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def run_count(self) -> int:
        """Total number of learning loop runs completed."""
        return self._run_count

    def compute_interval(self, gap_count: int) -> int:
        """Compute the fast interval in minutes based on current gap count.

        Higher gap count -> shorter interval (more frequent runs).
        Lower gap count -> longer interval (less frequent runs).

        Args:
            gap_count: Current number of unresolved knowledge gaps.

        Returns:
            Recommended fast interval in minutes, bounded between 1 and 30.
        """
        # Scale inversely with gap count: more gaps -> shorter interval
        # At 100+ gaps: 1 minute. At 0 gaps: 30 minutes.
        if gap_count >= 100:
            return _FAST_MIN_MINUTES
        if gap_count <= 0:
            return _FAST_MAX_MINUTES
        # Linear interpolation between min and max
        fraction = gap_count / 100.0
        interval = int(_FAST_MAX_MINUTES - fraction * (_FAST_MAX_MINUTES - _FAST_MIN_MINUTES))
        return max(_FAST_MIN_MINUTES, min(_FAST_MAX_MINUTES, interval))

    def _get_fast_interval(self) -> int:
        """Get the configured fast interval (minutes)."""
        if self._config is not None and hasattr(self._config, "daemon"):
            return self._config.daemon.fast_interval_minutes
        return 5  # default

    def _get_medium_interval(self) -> int:
        """Get the configured medium interval (minutes)."""
        if self._config is not None and hasattr(self._config, "daemon"):
            return self._config.daemon.medium_interval_minutes
        return 60  # default

    def _get_deep_interval(self) -> int:
        """Get the configured deep interval (minutes)."""
        if self._config is not None and hasattr(self._config, "daemon"):
            return self._config.daemon.deep_interval_minutes
        return 1440  # default

    def _is_adaptive(self) -> bool:
        """Whether adaptive frequency is enabled."""
        if self._config is not None and hasattr(self._config, "daemon"):
            return self._config.daemon.adaptive
        return True  # default

    def _run_loop(self) -> None:
        """Main scheduler loop — runs in background thread."""
        if self._db_path is None:
            logger.warning("No db_path configured — scheduler running in no-op mode")
            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=1)
            return

        # Open thread-local connection (RESEARCH pitfall 1)
        from db_wiki.core.store import init_schema, open_store
        conn = open_store(self._db_path)
        init_schema(conn)

        # Register jobs at configured intervals (D-05)
        fast = self._get_fast_interval()
        medium = self._get_medium_interval()
        deep = self._get_deep_interval()

        self._scheduler.every(fast).minutes.do(self._run_job, conn, "fast")
        self._scheduler.every(medium).minutes.do(self._run_job, conn, "medium")
        self._scheduler.every(deep).minutes.do(self._run_job, conn, "deep")

        logger.info(
            "Scheduled: fast=%dm, medium=%dm, deep=%dm",
            fast,
            medium,
            deep,
        )

        while not self._stop_event.is_set():
            self._scheduler.run_pending()
            # Check every second for stop signal
            self._stop_event.wait(timeout=1)

        conn.close()
        logger.info("Scheduler thread exiting")

    def _run_job(self, conn, frequency: str) -> None:
        """Execute one learning loop run."""
        from db_wiki.learning.orchestrator import run_learning_loop

        logger.info("Running %s learning loop", frequency)
        try:
            summary = run_learning_loop(conn, self._config)
            self._run_count += 1
            logger.info("Learning loop (%s) complete: %s", frequency, summary)

            # Adaptive frequency (D-05): adjust intervals based on gap count
            if self._is_adaptive():
                self._adapt_frequency(conn)
        except Exception:
            logger.exception("Learning loop (%s) failed", frequency)

    def _adapt_frequency(self, conn) -> None:
        """Adjust scheduling frequency based on gap count trend (D-05).

        If gap count is increasing, decrease fast interval (more frequent).
        If gap count is stable or decreasing, increase fast interval (less frequent).
        Bounds: fast interval stays between 1 and 30 minutes.
        """
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM knowledge_gaps WHERE resolution IS NULL"
            ).fetchone()
            current_gaps = row["cnt"] if row else 0

            if self._last_gap_count is not None and self._config is not None:
                if current_gaps > self._last_gap_count:
                    # More gaps — increase frequency (shorter interval)
                    new_fast = max(
                        _FAST_MIN_MINUTES,
                        self._config.daemon.fast_interval_minutes - 1,
                    )
                    self._config.daemon.fast_interval_minutes = new_fast
                    logger.info("Adaptive: gaps increasing, fast=%dm", new_fast)
                elif current_gaps < self._last_gap_count:
                    # Fewer gaps — decrease frequency (longer interval)
                    new_fast = min(
                        _FAST_MAX_MINUTES,
                        self._config.daemon.fast_interval_minutes + 2,
                    )
                    self._config.daemon.fast_interval_minutes = new_fast
                    logger.info("Adaptive: gaps decreasing, fast=%dm", new_fast)

            self._last_gap_count = current_gaps
        except Exception:
            logger.debug("Adaptive frequency check failed", exc_info=True)
