"""Background thread: calendar e-mail reminders (hourly)."""

from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 3600

_poller_thread: threading.Thread | None = None


def _run_once() -> None:
    from app.calendar_email_alert_service import process_due_calendar_notifications
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        n = process_due_calendar_notifications(db)
        db.commit()
        if n:
            log.info("calendar_notification_job: sent %s reminder e-mail(s)", n)
    except Exception:
        log.exception("calendar_notification_job: run failed")
        db.rollback()
    finally:
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
