"""Phase 5 Wave 0 test stubs for background daemon/scheduler (LEARN-13).

All tests are marked xfail — they verify the contracts that the Phase 5
daemon implementation must satisfy.
"""
import pytest


XFAIL_REASON = "Phase 5 Wave 0 stub — not yet implemented"


# ---------------------------------------------------------------------------
# LEARN-13: Scheduler lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_scheduler_starts():
    """DaemonScheduler.start() creates and starts a background thread. (LEARN-13)"""
    from db_wiki.daemon.scheduler import DaemonScheduler

    sched = DaemonScheduler()
    try:
        sched.start()
        assert sched._thread is not None
        assert sched._thread.is_alive()
    finally:
        sched.stop()


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_scheduler_stops():
    """DaemonScheduler.stop() sets _stop_event after start(). (LEARN-13)"""
    from db_wiki.daemon.scheduler import DaemonScheduler

    sched = DaemonScheduler()
    sched.start()
    sched.stop()
    assert sched._stop_event.is_set()


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_scheduler_uses_instance_scheduler():
    """DaemonScheduler uses schedule.Scheduler() instance, not global schedule module. (LEARN-13)"""
    import schedule as schedule_lib

    from db_wiki.daemon.scheduler import DaemonScheduler

    sched = DaemonScheduler()
    # The scheduler must not share the global default scheduler
    assert isinstance(sched._scheduler, schedule_lib.Scheduler)
    assert sched._scheduler is not schedule_lib.default_scheduler


@pytest.mark.xfail(reason=XFAIL_REASON, strict=True)
def test_scheduler_adaptive_frequency():
    """DaemonScheduler adjusts run intervals based on gap count. (D-05)"""
    from db_wiki.daemon.scheduler import DaemonScheduler

    sched = DaemonScheduler()
    # High gap count → more frequent runs
    interval_high_gaps = sched.compute_interval(gap_count=100)
    # Low gap count → less frequent runs
    interval_low_gaps = sched.compute_interval(gap_count=5)
    assert interval_high_gaps < interval_low_gaps
