"""Tests for Docker bind-mount host path resolution from container mountinfo."""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.local_compose_update import (
    _host_path_for_compose_project,
    _normalize_mount_root_for_docker_bind,
)


def test_normalize_btrfs_home_subvolume() -> None:
    assert _normalize_mount_root_for_docker_bind("/@home/colin/canarycms") == "/home/colin/canarycms"


def test_normalize_regular_path_unchanged() -> None:
    assert _normalize_mount_root_for_docker_bind("/var/lib/canary") == "/var/lib/canary"


def test_explicit_host_project_dir_for_compose_mount(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_COMPOSE_HOST_PROJECT_DIR", "/host/proj")
    monkeypatch.setenv("CANARY_COMPOSE_PROJECT_DIR", "/canary-compose")
    assert _host_path_for_compose_project(Path("/canary-compose")) == "/host/proj"


def test_runtime_subdir_maps_under_host_project_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """``.canary/runtime`` is under the compose project mount and maps with the host override."""
    monkeypatch.setenv("CANARY_COMPOSE_HOST_PROJECT_DIR", "/host/proj")
    monkeypatch.setenv("CANARY_COMPOSE_PROJECT_DIR", "/canary-compose")
    assert _host_path_for_compose_project(Path("/canary-compose/.canary/runtime")) == (
        "/host/proj/.canary/runtime"
    )
