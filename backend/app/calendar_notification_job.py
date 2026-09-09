"""Background thread: calendar e-mail reminders (hourly)."""

from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import text

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 3600
_ADVISORY_LOCK_KEY = 910017702

_poller_thread: threading.Thread | None = None


def _run_once() -> None:
    from app.calendar_email_alert_service import process_due_calendar_notifications
    from app.db import SessionLocal, engine

    db = SessionLocal()
    locked = False
    try:
        if engine.dialect.name != "postgresql":
            n = process_due_calendar_notifications(db)
            db.commit()
            if n:
                log.info("calendar_notification_job: sent %s reminder e-mail(s)", n)
            return
        got = db.execute(text(f"SELECT pg_try_advisory_lock({_ADVISORY_LOCK_KEY})")).scalar()
        if not got:
            return
        locked = True
        n = process_due_calendar_notifications(db)
        db.commit()
        if n:
            log.info("calendar_notification_job: sent %s reminder e-mail(s)", n)
    except Exception:
        log.exception("calendar_notification_job: run failed")
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
    log.warning("calendar_notification_job: thread started")
    time.sleep(120)
    while True:
        try:
            _run_once()
        except Exception:
            log.exception("calendar_notification_job: unexpected error")
        time.sleep(INTERVAL_SECONDS)


def start_calendar_notification_job() -> None:
    global _poller_thread
    if _poller_thread is not None and _poller_thread.is_alive():
        return
    _poller_thread = threading.Thread(
        target=_thread_main,
        name="calendar-notification-job",
        daemon=True,
    )
    _poller_thread.start()
    log.warning("calendar_notification_job: background thread started")
