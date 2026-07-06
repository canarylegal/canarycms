"""Tests for Admin deploy update-check payload (GitHub API mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.github_update_check import _same_commit, build_update_check_payload


def test_same_commit_short_sha_prefix() -> None:
    full = "d8290106768ecc9bb8374451bf8174483df80ca5"
    short = "d829010"
    assert _same_commit(full, short)
    assert _same_commit(short, full)


@patch("app.github_update_check.compose_git_reset_enabled", return_value=False)
@patch("app.github_update_check.load_compose_update_config")
@patch("app.github_update_check.compose_update_configured", return_value=True)
@patch("app.github_update_check.load_github_repo_for_api", return_value=("owner", "repo", "main"))
@patch("app.github_update_check.effective_build_commit_for_update_check", return_value="aaa1111")
@patch("app.github_update_check.httpx.Client")
def test_update_not_available_when_current_matches_remote(
    client_cls: MagicMock,
    _current: object,
    _repo: object,
    _compose: object,
    mock_cfg: MagicMock,
    _reset: object,
) -> None:
    mock_cfg.return_value = MagicMock(git_ref="main")
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
    assert payload["current_commit"] == "aaa1111"
    assert payload["remote_commit"] == sha


@patch("app.github_update_check.compose_git_reset_enabled", return_value=False)
@patch("app.github_update_check.load_compose_update_config")
@patch("app.github_update_check.compose_update_configured", return_value=True)
@patch("app.github_update_check.load_github_repo_for_api", return_value=("owner", "repo", "main"))
@patch("app.github_update_check.effective_build_commit_for_update_check", return_value="olddeadbeef")
@patch("app.github_update_check.httpx.Client")
def test_update_available_when_remote_ahead(
    client_cls: MagicMock,
    _current: object,
    _repo: object,
    _compose: object,
    mock_cfg: MagicMock,
    _reset: object,
) -> None:
    mock_cfg.return_value = MagicMock(git_ref="main")
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


@patch("app.github_update_check.compose_git_reset_enabled", return_value=False)
@patch("app.github_update_check.load_compose_update_config")
@patch("app.github_update_check.compose_update_configured", return_value=True)
@patch("app.github_update_check.load_github_repo_for_api", return_value=("owner", "repo", "main"))
@patch("app.github_update_check.effective_build_commit_for_update_check", return_value="localonly")
@patch("app.github_update_check.httpx.Client")
def test_update_not_available_when_local_ahead_of_remote(
    client_cls: MagicMock,
    _current: object,
    _repo: object,
    _compose: object,
    mock_cfg: MagicMock,
    _reset: object,
) -> None:
    mock_cfg.return_value = MagicMock(git_ref="main")
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
