"""Tests for Docker bind-mount host path resolution from container mountinfo."""

from app.local_compose_update import _normalize_mount_root_for_docker_bind


def test_normalize_btrfs_home_subvolume() -> None:
    assert _normalize_mount_root_for_docker_bind("/@home/colin/canarycms") == "/home/colin/canarycms"


def test_normalize_regular_path_unchanged() -> None:
    assert _normalize_mount_root_for_docker_bind("/var/lib/canary") == "/var/lib/canary"
