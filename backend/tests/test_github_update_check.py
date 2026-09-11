"""Tests for Admin deploy update-check payload (GitHub API mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.github_update_check import _same_commit, build_update_check_payload
from app.local_compose_update import compose_update_configured, load_compose_update_config


def test_same_commit_short_sha_prefix() -> None:
    full = "d8290106768ecc9bb8374451bf8174483df80ca5"
    short = "d829010"
    assert _same_commit(full, short)
    assert _same_commit(short, full)


def test_compose_gui_update_permanently_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    # Env cannot re-enable GUI updates.
    monkeypatch.setenv("CANARY_COMPOSE_UPDATE_ENABLED", "1")
    monkeypatch.setenv("CANARY_COMPOSE_PROJECT_DIR", "/tmp")
    assert compose_update_configured() is False
    assert load_compose_update_config() is None


@patch("app.github_update_check.load_github_repo_for_api", return_value=("owner", "repo", "main"))
@patch("app.github_update_check.effective_build_commit_for_update_check", return_value="aaa1111")
@patch("app.github_update_check.httpx.Client")
def test_update_not_available_when_current_matches_remote(
    client_cls: MagicMock,
    _current: object,
    _repo: object,
) -> None:
    sha = "aaa1111" + ("0" * 33)
    mock_client = MagicMock()
    client_cls.return_value.__enter__.return_value = mock_client

    tip_resp = MagicMock()
    tip_resp.status_code = 200
    tip_resp.json.return_value = {"sha": sha}

    cmp_resp = MagicMock()
    cmp_resp.status_code = 200
    cmp_resp.json.return_value = {"ahead_by": 0, "behind_by": 0, "commits": []}

    rel_resp = MagicMock()
    rel_resp.status_code = 404

    mock_client.get.side_effect = lambda url, **_: (
        tip_resp if url.endswith("/commits/main") else cmp_resp if "/compare/" in url else rel_resp
    )

    payload = build_update_check_payload()
    assert payload["update_available"] is False
    assert payload["compose_update_enabled"] is False
    assert payload["deploy_trigger_configured"] is False
    assert payload["current_commit"] == "aaa1111"
    assert payload["remote_commit"] == sha


@patch("app.github_update_check.load_github_repo_for_api", return_value=("owner", "repo", "main"))
@patch("app.github_update_check.effective_build_commit_for_update_check", return_value="olddeadbeef")
@patch("app.github_update_check.httpx.Client")
def test_update_available_when_remote_ahead(
    client_cls: MagicMock,
    _current: object,
    _repo: object,
) -> None:
    mock_client = MagicMock()
    client_cls.return_value.__enter__.return_value = mock_client

    tip_resp = MagicMock()
    tip_resp.status_code = 200
    tip_resp.json.return_value = {"sha": "b" * 40}

    cmp_resp = MagicMock()
    cmp_resp.status_code = 200
    cmp_resp.json.return_value = {
        "html_url": "https://github.com/o/r/compare/old..new",
        "commits": [],
        "ahead_by": 2,
        "behind_by": 0,
    }

    rel_resp = MagicMock()
    rel_resp.status_code = 404

    def fake_get(url: str, **kwargs: object) -> MagicMock:
        if "/compare/" in url:
            return cmp_resp
        if "/commits/main" in url:
            return tip_resp
        return rel_resp

    mock_client.get.side_effect = fake_get

    payload = build_update_check_payload()
    assert payload["update_available"] is True
    assert payload["compare_html_url"] == "https://github.com/o/r/compare/old..new"


@patch("app.github_update_check.load_github_repo_for_api", return_value=("owner", "repo", "latest-release"))
@patch("app.github_update_check.effective_build_commit_for_update_check", return_value="aaa1111")
@patch("app.github_update_check.httpx.Client")
def test_latest_release_ref_compares_to_release_tag(
    client_cls: MagicMock,
    _current: object,
    _repo: object,
) -> None:
    sha = "aaa1111" + ("0" * 33)
    mock_client = MagicMock()
    client_cls.return_value.__enter__.return_value = mock_client

    rel_resp = MagicMock()
    rel_resp.status_code = 200
    rel_resp.json.return_value = {
        "tag_name": "v1.0.0",
        "name": "Canary CMS v1.0.0",
        "body": "baseline",
    }

    tip_resp = MagicMock()
    tip_resp.status_code = 200
    tip_resp.json.return_value = {"sha": sha}

    cmp_resp = MagicMock()
    cmp_resp.status_code = 200
    cmp_resp.json.return_value = {"ahead_by": 0, "behind_by": 0, "commits": []}

    def fake_get(url: str, **kwargs: object) -> MagicMock:
        if url.endswith("/releases/latest"):
            return rel_resp
        if "/commits/v1.0.0" in url:
            return tip_resp
        if "/compare/" in url:
            return cmp_resp
        return MagicMock(status_code=404)

    mock_client.get.side_effect = fake_get

    payload = build_update_check_payload()
    assert payload["update_available"] is False
    assert payload["remote_ref"] == "v1.0.0"
    assert payload["latest_release_tag"] == "v1.0.0"
    assert payload["compose_git_ref"] == "v1.0.0"


@patch("app.github_update_check.load_github_repo_for_api", return_value=("owner", "repo", "main"))
@patch("app.github_update_check.effective_build_commit_for_update_check", return_value="localonly")
@patch("app.github_update_check.httpx.Client")
def test_update_not_available_when_local_ahead_of_remote(
    client_cls: MagicMock,
    _current: object,
    _repo: object,
) -> None:
    mock_client = MagicMock()
    client_cls.return_value.__enter__.return_value = mock_client

    tip_resp = MagicMock()
    tip_resp.status_code = 200
    tip_resp.json.return_value = {"sha": "b" * 40}

    cmp_resp = MagicMock()
    cmp_resp.status_code = 200
    cmp_resp.json.return_value = {
        "ahead_by": 0,
        "behind_by": 1,
        "commits": [],
    }

    rel_resp = MagicMock()
    rel_resp.status_code = 404

    def fake_get(url: str, **kwargs: object) -> MagicMock:
        if "/compare/" in url:
            return cmp_resp
        if "/commits/main" in url:
            return tip_resp
        return rel_resp

    mock_client.get.side_effect = fake_get

    payload = build_update_check_payload()
    assert payload["update_available"] is False
    assert "ahead of GitHub" in (payload.get("note") or "")
    assert "Reset to GitHub" not in (payload.get("note") or "")
