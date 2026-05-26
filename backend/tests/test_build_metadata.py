"""Tests for build commit resolution (health vs update-check precedence)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.build_metadata import (
    effective_build_commit,
    effective_build_commit_for_update_check,
    invalidate_live_compose_repo_head_cache,
)


@pytest.fixture(autouse=True)
def _clear_live_head_cache() -> None:
    invalidate_live_compose_repo_head_cache()


def test_effective_build_commit_prefers_live_mount_over_baked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_BUILD_COMMIT", "bakeddeadbeef")
    monkeypatch.delenv("CANARY_BUILD_COMMIT_OVERRIDE", raising=False)
    with patch("app.build_metadata._live_compose_repo_head", return_value="livecafebabe"):
        assert effective_build_commit() == "livecafebabe"


def test_update_check_prefers_baked_over_live_mount(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_BUILD_COMMIT", "bakeddeadbeef")
    monkeypatch.delenv("CANARY_BUILD_COMMIT_OVERRIDE", raising=False)
    with patch("app.build_metadata._live_compose_repo_head", return_value="livecafebabe"):
        assert effective_build_commit_for_update_check() == "bakeddeadbeef"


def test_update_check_falls_back_to_live_when_baked_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_BUILD_COMMIT", "unknown")
    monkeypatch.delenv("CANARY_BUILD_COMMIT_OVERRIDE", raising=False)
    with patch("app.build_metadata._live_compose_repo_head", return_value="livecafebabe"):
        assert effective_build_commit_for_update_check() == "livecafebabe"


def test_update_check_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_BUILD_COMMIT_OVERRIDE", "override123")
    monkeypatch.setenv("CANARY_BUILD_COMMIT", "bakeddeadbeef")
    with patch("app.build_metadata._live_compose_repo_head", return_value="livecafebabe"):
        assert effective_build_commit_for_update_check() == "override123"


def test_update_check_unknown_when_baked_and_live_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CANARY_BUILD_COMMIT", raising=False)
    monkeypatch.delenv("CANARY_BUILD_COMMIT_OVERRIDE", raising=False)
    with patch("app.build_metadata._live_compose_repo_head", return_value=None):
        assert effective_build_commit_for_update_check() == "unknown"
