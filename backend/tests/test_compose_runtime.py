"""Compose update runtime paths (not user file storage)."""

from pathlib import Path

import pytest

from app.compose_runtime import (
    compose_job_state_path,
    compose_project_dir,
    compose_runtime_dir,
    compose_up_marker_path,
)


def test_runtime_dir_under_compose_project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CANARY_COMPOSE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("CANARY_COMPOSE_RUNTIME_DIR", raising=False)
    rt = compose_runtime_dir()
    assert rt == (tmp_path / ".canary" / "runtime").resolve()
    assert rt.is_dir()
    assert compose_job_state_path() == rt / "compose-job-state.json"
    assert compose_up_marker_path("abc") == rt / "compose-up-abc.json"


def test_runtime_dir_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom = tmp_path / "state"
    monkeypatch.setenv("CANARY_COMPOSE_RUNTIME_DIR", str(custom))
    assert compose_runtime_dir() == custom.resolve()


def test_compose_project_dir_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CANARY_COMPOSE_PROJECT_DIR", str(tmp_path))
    assert compose_project_dir() == tmp_path.resolve()
