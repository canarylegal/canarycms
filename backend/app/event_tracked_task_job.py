"""Background thread: refresh case-task priority/due for tracked case events (hourly)."""

from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import text

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 3600
_ADVISORY_LOCK_KEY = 910017701

_poller_thread: threading.Thread | None = None


def _run_once() -> None:
    from app.db import SessionLocal
    from app.event_tracked_tasks import refresh_tracked_event_tasks

    db = SessionLocal()
    locked = False
    try:
        # Skip when another replica/worker already holds the lock (Postgres only).
        try:
            got = db.execute(text(f"SELECT pg_try_advisory_lock({_ADVISORY_LOCK_KEY})")).scalar()
        except Exception:
            got = True
        if not got:
            return
        locked = bool(got)
        refresh_tracked_event_tasks(db)
    except Exception:
        log.exception("event_tracked_task_job: run failed")
        db.rollback()
    finally:
        if locked:
            try:
                db.execute(text(f"SELECT pg_advisory_unlock({_ADVISORY_LOCK_KEY})"))
                db.commit()
            except Exception:
                db.rollback()
        db.close()


def _thread_main() -> None:
    log.warning("event_tracked_task_job: thread started")
    time.sleep(45)
    while True:
        try:
            _run_once()
        except Exception:
            log.exception("event_tracked_task_job: unexpected error")
        time.sleep(INTERVAL_SECONDS)


def start_event_tracked_task_job() -> None:
    global _poller_thread
    if _poller_thread is not None and _poller_thread.is_alive():
        return
    _poller_thread = threading.Thread(
        target=_thread_main,
        name="event-tracked-task-job",
        daemon=True,
    )
    _poller_thread.start()
    log.warning("event_tracked_task_job: background thread started")
