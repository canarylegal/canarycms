"""Tests for compose update git sync (ff-only vs reset)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.local_compose_update import ComposeUpdateConfig, _run_git_sync, _subprocess_failure_message, run_compose_update


@pytest.fixture
def compose_cfg(tmp_path: Path) -> ComposeUpdateConfig:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return ComposeUpdateConfig(
        project_dir=repo,
        compose_files=("docker-compose.yml",),
        profiles=("prod",),
        git_pull=True,
        git_reset_enabled=True,
        git_ref="main",
    )


def test_run_git_sync_ff_only(compose_cfg: ComposeUpdateConfig) -> None:
    journal: list[str] = []
    with patch("app.local_compose_update.shutil.which", return_value="/usr/bin/git"):
        with patch("app.local_compose_update.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            _run_git_sync(compose_cfg, journal, "ff-only")
    assert run.call_count == 1
    args = run.call_args[0][0]
    assert "pull" in args
    assert "--ff-only" in args
    assert "origin" in args
    assert "main" in args
    assert journal[0].startswith("git: pull")


def test_run_git_sync_reset(compose_cfg: ComposeUpdateConfig) -> None:
    journal: list[str] = []
    with patch("app.local_compose_update.shutil.which", return_value="/usr/bin/git"):
        with patch("app.local_compose_update.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            _run_git_sync(compose_cfg, journal, "reset")
    assert run.call_count == 2
    fetch_args = run.call_args_list[0][0][0]
    reset_args = run.call_args_list[1][0][0]
    assert "fetch" in fetch_args and "origin" in fetch_args and "main" in fetch_args
    assert "reset" in reset_args and "FETCH_HEAD" in reset_args
    assert any("reset finished" in line for line in journal)


def test_subprocess_failure_message_prefers_build_errors() -> None:
    exc = subprocess.CalledProcessError(
        2,
        ["docker", "compose", "build"],
        output="Downloading websockets\n#27 ERROR: npm run build failed\nsrc/foo.ts(1,1): error TS2322: bad type\n",
    )
    msg = _subprocess_failure_message("docker-compose build --pull", exc)
    assert "error TS2322" in msg
    assert "Downloading websockets" not in msg


def test_run_compose_update_reset_requires_flag(compose_cfg: ComposeUpdateConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_no_reset = ComposeUpdateConfig(
        project_dir=compose_cfg.project_dir,
        compose_files=compose_cfg.compose_files,
        profiles=compose_cfg.profiles,
        git_pull=True,
        git_reset_enabled=False,
        git_ref="main",
    )
    monkeypatch.setenv("CANARY_COMPOSE_UPDATE_ENABLED", "1")
    monkeypatch.setenv("CANARY_COMPOSE_PROJECT_DIR", str(compose_cfg.project_dir))
    (compose_cfg.project_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    with patch("app.local_compose_update.load_compose_update_config", return_value=cfg_no_reset):
        with pytest.raises(RuntimeError, match="Git reset is not enabled"):
            run_compose_update(git_strategy="reset")
