"""Tests for compose deploy job disk state and reconciliation (no Docker daemon required)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import app.compose_deploy_job as job_mod
from app.compose_deploy_job import (
    _read_disk_state,
    _write_disk_state,
    get_compose_job_public,
    reconcile_compose_job_state,
)
from app.compose_runtime import compose_job_state_path, compose_up_marker_path


@pytest.fixture(autouse=True)
def _reset_in_memory_job() -> None:
    with job_mod._lock:
        job_mod._job_id = None
        job_mod._phase = "idle"
        job_mod._started_at = None
        job_mod._finished_at = None
        job_mod._message = None
        job_mod._error_detail = None
        job_mod._log_excerpt = None
        job_mod._runner_expected = False
        job_mod._journal_lines = []
        job_mod._progress_phase = None


@pytest.fixture
def compose_state_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    """Isolated runtime dir + compose project dir for legacy mirror paths."""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("CANARY_COMPOSE_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("CANARY_COMPOSE_PROJECT_DIR", str(project))
    return runtime, project


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_read_disk_state_prefers_primary_running_over_legacy_succeeded(
    compose_state_layout: tuple[Path, Path],
) -> None:
    runtime, project = compose_state_layout
    _write_json(
        project / ".canary-compose-job-state.json",
        {"status": "succeeded", "job_id": "oldjob", "started_at": "2020-01-01T00:00:00+00:00"},
    )
    _write_json(
        compose_job_state_path(),
        {
            "status": "running",
            "job_id": "newjob",
            "started_at": "2026-01-01T00:00:00+00:00",
            "runner_expected": True,
        },
    )
    row = _read_disk_state()
    assert row is not None
    assert row["status"] == "running"
    assert row["job_id"] == "newjob"


def test_read_disk_state_falls_back_to_legacy_when_primary_missing(
    compose_state_layout: tuple[Path, Path],
) -> None:
    _runtime, project = compose_state_layout
    _write_json(
        project / ".canary-compose-job-state.json",
        {"status": "failed", "job_id": "legacyonly", "started_at": "2026-01-01T00:00:00+00:00"},
    )
    row = _read_disk_state()
    assert row is not None
    assert row["status"] == "failed"
    assert row["job_id"] == "legacyonly"


def test_write_disk_state_does_not_update_legacy_mirror(
    compose_state_layout: tuple[Path, Path],
) -> None:
    _runtime, project = compose_state_layout
    legacy = project / ".canary-compose-job-state.json"
    _write_json(legacy, {"status": "succeeded", "job_id": "stale", "started_at": "2020-01-01T00:00:00+00:00"})
    legacy_text = legacy.read_text(encoding="utf-8")

    _write_disk_state(
        {
            "status": "running",
            "job_id": "fresh",
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": None,
            "message": None,
            "error_detail": None,
            "log_excerpt": None,
            "runner_expected": True,
        }
    )

    assert legacy.read_text(encoding="utf-8") == legacy_text
    primary = compose_job_state_path()
    assert primary.is_file()
    assert json.loads(primary.read_text(encoding="utf-8"))["job_id"] == "fresh"


@patch("app.compose_deploy_job.subprocess.run")
@patch("app.compose_deploy_job.docker_inspect_container_state", return_value=None)
def test_reconcile_success_marker_finalizes_job(
    _inspect: object,
    _subprocess: object,
    compose_state_layout: tuple[Path, Path],
) -> None:
    jid = "abc123"
    _write_json(
        compose_job_state_path(),
        {
            "status": "running",
            "job_id": jid,
            "started_at": "2026-01-01T00:00:00+00:00",
            "host_boot_id": "boot-a",
            "runner_expected": True,
        },
    )
    marker = compose_up_marker_path(jid)
    marker.write_text('{"ok": true, "rc": 0}', encoding="utf-8")

    with patch("app.compose_deploy_job._host_boot_id", return_value="boot-b"):
        reconcile_compose_job_state()

    pub = get_compose_job_public()
    assert pub["status"] == "succeeded"
    assert pub["job_id"] == jid
    assert not marker.is_file()
    disk = json.loads(compose_job_state_path().read_text(encoding="utf-8"))
    assert disk["status"] == "succeeded"


@patch("app.compose_deploy_job.subprocess.run")
@patch("app.compose_deploy_job.docker_inspect_container_state", return_value=None)
def test_reconcile_failure_marker_finalizes_job(
    _inspect: object,
    _subprocess: object,
    compose_state_layout: tuple[Path, Path],
) -> None:
    jid = "fail99"
    _write_json(
        compose_job_state_path(),
        {
            "status": "running",
            "job_id": jid,
            "started_at": "2026-01-01T00:00:00+00:00",
            "host_boot_id": "boot-a",
            "runner_expected": True,
        },
    )
    marker = compose_up_marker_path(jid)
    marker.write_text('{"ok": false, "rc": 1}', encoding="utf-8")

    with patch("app.compose_deploy_job._host_boot_id", return_value="boot-b"):
        reconcile_compose_job_state()

    pub = get_compose_job_public()
    assert pub["status"] == "failed"
    assert pub["job_id"] == jid
    assert pub["error_detail"] is not None
    assert "rc=1" in pub["error_detail"]


def test_running_payload_includes_live_journal_from_disk(
    compose_state_layout: tuple[Path, Path],
) -> None:
    _write_json(
        compose_job_state_path(),
        {
            "status": "running",
            "job_id": "live1",
            "started_at": "2026-01-01T00:00:00+00:00",
            "journal_lines": ["git: pull --ff-only (starting)"],
            "progress_phase": "git",
        },
    )
    pub = get_compose_job_public()
    assert pub["status"] == "running"
    assert pub["journal_lines"] == ["git: pull --ff-only (starting)"]
    assert pub["progress_phase"] == "git"
    assert pub["elapsed_seconds"] is not None
