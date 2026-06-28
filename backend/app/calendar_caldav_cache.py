"""Short-lived in-process cache for CalDAV calendar event fetches (Radicale is slow)."""
from __future__ import annotations

import copy
import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_TTL_SECONDS = float(os.getenv("CALDAV_EVENTS_CACHE_SECONDS", "60"))
_SYNC_INTERVAL_SECONDS = float(os.getenv("CALENDAR_REMOTE_SYNC_INTERVAL_SECONDS", "300"))
_sync_last_by_user: dict[uuid.UUID, float] = {}
_lock = threading.Lock()
_by_key: dict[tuple[str, str, str, tuple[tuple[str, str, str], ...]], _CacheEntry] = {}


@dataclass
class _CacheEntry:
    expires_at: float
    items: list[dict[str, Any]]


def _cache_key(
    dav_user_id: uuid.UUID,
    items: list[tuple[str, str, str]],
    range_start: datetime,
    range_end: datetime,
) -> tuple[str, str, str, tuple[tuple[str, str, str], ...]]:
    rs = range_start.isoformat()
    re = range_end.isoformat()
    slugs = tuple(sorted((slug, display_name, calendar_id) for slug, display_name, calendar_id in items))
    return (str(dav_user_id), rs, re, slugs)


def get_cached_events(
    dav_user_id: uuid.UUID,
    items: list[tuple[str, str, str]],
    range_start: datetime,
    range_end: datetime,
) -> list[dict[str, Any]] | None:
    if _TTL_SECONDS <= 0:
        return None
    key = _cache_key(dav_user_id, items, range_start, range_end)
    now = time.monotonic()
    with _lock:
        entry = _by_key.get(key)
        if entry is None or entry.expires_at <= now:
            if entry is not None:
                del _by_key[key]
            return None
        return copy.deepcopy(entry.items)


def store_cached_events(
    dav_user_id: uuid.UUID,
    items: list[tuple[str, str, str]],
    range_start: datetime,
    range_end: datetime,
    result: list[dict[str, Any]],
) -> None:
    if _TTL_SECONDS <= 0:
        return
    key = _cache_key(dav_user_id, items, range_start, range_end)
    with _lock:
        _by_key[key] = _CacheEntry(expires_at=time.monotonic() + _TTL_SECONDS, items=copy.deepcopy(result))


def invalidate_caldav_events_cache(*, dav_user_id: uuid.UUID | None = None) -> None:
    """Drop cached event lists; pass ``dav_user_id`` to clear one principal only."""
    with _lock:
        if dav_user_id is None:
            _by_key.clear()
            return
        uid = str(dav_user_id)
        for key in [k for k in _by_key if k[0] == uid]:
            del _by_key[key]


def should_skip_remote_calendar_sync(user_id: uuid.UUID) -> bool:
    if _SYNC_INTERVAL_SECONDS <= 0:
        return False
    now = time.monotonic()
    with _lock:
        last = _sync_last_by_user.get(user_id)
        return last is not None and (now - last) < _SYNC_INTERVAL_SECONDS


def mark_remote_calendar_synced(user_id: uuid.UUID) -> None:
    with _lock:
        _sync_last_by_user[user_id] = time.monotonic()
