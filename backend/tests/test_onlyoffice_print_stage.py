"""ONLYOFFICE print-staging memory budgets."""

from __future__ import annotations

import time

import pytest

from app.routers import onlyoffice as oo


@pytest.fixture(autouse=True)
def _clear_print_store() -> None:
    with oo._PRINT_STORE_LOCK:
        oo._PRINT_STORE.clear()
    yield
    with oo._PRINT_STORE_LOCK:
        oo._PRINT_STORE.clear()


def test_print_store_accepts_within_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oo, "_PRINT_STAGING_MAX_TOTAL_BYTES", 1024)
    monkeypatch.setattr(oo, "_PRINT_STAGING_MAX_PER_USER", 4)
    assert oo._print_store_accepts_unlocked(user_id="u1", new_bytes=512) is None


def test_print_store_rejects_aggregate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oo, "_PRINT_STAGING_MAX_TOTAL_BYTES", 100)
    monkeypatch.setattr(oo, "_PRINT_STAGING_MAX_PER_USER", 10)
    with oo._PRINT_STORE_LOCK:
        oo._PRINT_STORE["a"] = (b"x" * 80, time.time() + 60, "u1")
    assert oo._print_store_accepts_unlocked(user_id="u2", new_bytes=40) == "aggregate_limit"


def test_print_store_rejects_per_user_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oo, "_PRINT_STAGING_MAX_TOTAL_BYTES", 10_000)
    monkeypatch.setattr(oo, "_PRINT_STAGING_MAX_PER_USER", 2)
    with oo._PRINT_STORE_LOCK:
        oo._PRINT_STORE["a"] = (b"one", time.time() + 60, "u1")
        oo._PRINT_STORE["b"] = (b"two", time.time() + 60, "u1")
    assert oo._print_store_accepts_unlocked(user_id="u1", new_bytes=10) == "per_user_limit"
    assert oo._print_store_accepts_unlocked(user_id="u2", new_bytes=10) is None


def test_print_store_gc_frees_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oo, "_PRINT_STAGING_MAX_TOTAL_BYTES", 100)
    monkeypatch.setattr(oo, "_PRINT_STAGING_MAX_PER_USER", 10)
    with oo._PRINT_STORE_LOCK:
        oo._PRINT_STORE["stale"] = (b"x" * 90, time.time() - 1, "u1")
        oo._gc_print_store_unlocked(time.time())
        assert oo._PRINT_STORE == {}
    assert oo._print_store_accepts_unlocked(user_id="u1", new_bytes=90) is None
