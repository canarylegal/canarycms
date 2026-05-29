"""Tests for compose update progress phase heuristics."""

from __future__ import annotations

from app.compose_deploy_progress import compose_phase_from_journal


def test_phase_starts_at_build_without_git() -> None:
    assert compose_phase_from_journal([]) == "build"
    assert compose_phase_from_journal(["docker-compose: build --pull (starting)"]) == "build"


def test_phase_git_then_build_then_up() -> None:
    lines = [
        "git: pull --ff-only (starting)",
        "git: pull finished",
        "docker-compose: build --pull (starting)",
    ]
    assert compose_phase_from_journal(lines) == "build"

    lines.append("docker-compose: build --pull (finished)")
    assert compose_phase_from_journal(lines) == "up"

    lines.append("docker-compose: up -d (starting)")
    assert compose_phase_from_journal(lines) == "up"


def test_phase_reset_git_lines() -> None:
    lines = [
        "git: fetch origin main + reset --hard FETCH_HEAD (starting)",
        "git: reset finished (origin/main)",
        "docker-compose: build --pull (starting)",
    ]
    assert compose_phase_from_journal(lines) == "build"
