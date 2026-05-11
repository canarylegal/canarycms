"""Trigger GitHub Actions ``workflow_dispatch`` for host deployment (Option A)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class GitHubDeployConfig:
    token: str
    owner: str
    repo: str
    workflow: str
    default_ref: str


def load_github_repo_for_api() -> tuple[str, str, str, str | None] | None:
    """``owner``, ``repo``, ``default_ref``, optional ``token`` for GitHub REST reads (token may be None on public repos)."""
    owner = (os.getenv("CANARY_GITHUB_DEPLOY_OWNER") or "").strip()
    repo = (os.getenv("CANARY_GITHUB_DEPLOY_REPO") or "").strip()
    if not owner or not repo:
        return None
    ref = (os.getenv("CANARY_GITHUB_DEPLOY_REF") or "main").strip() or "main"
    token = (os.getenv("CANARY_GITHUB_DEPLOY_TOKEN") or "").strip() or None
    return owner, repo, ref, token


def load_github_deploy_config() -> GitHubDeployConfig | None:
    token = (os.getenv("CANARY_GITHUB_DEPLOY_TOKEN") or "").strip()
    owner = (os.getenv("CANARY_GITHUB_DEPLOY_OWNER") or "").strip()
    repo = (os.getenv("CANARY_GITHUB_DEPLOY_REPO") or "").strip()
    workflow = (os.getenv("CANARY_GITHUB_DEPLOY_WORKFLOW") or "deploy-canary.yml").strip()
    default_ref = (os.getenv("CANARY_GITHUB_DEPLOY_REF") or "main").strip()
    if not token or not owner or not repo:
        return None
    return GitHubDeployConfig(
        token=token,
        owner=owner,
        repo=repo,
        workflow=workflow,
        default_ref=default_ref,
    )


def github_deploy_status_public() -> dict[str, Any]:
    """Safe fields for the admin UI (no token)."""
    cfg = load_github_deploy_config()
    if cfg is None:
        return {
            "configured": False,
            "owner": None,
            "repo": None,
            "workflow": None,
            "default_ref": None,
        }
    return {
        "configured": True,
        "owner": cfg.owner,
        "repo": cfg.repo,
        "workflow": cfg.workflow,
        "default_ref": cfg.default_ref,
    }


def trigger_workflow_dispatch(*, ref: str, environment: str) -> None:
    """POST workflow_dispatch; raises ``httpx.HTTPStatusError`` on failure."""
    cfg = load_github_deploy_config()
    if cfg is None:
        raise RuntimeError("GitHub deploy is not configured (missing CANARY_GITHUB_DEPLOY_* env).")

    url = f"https://api.github.com/repos/{cfg.owner}/{cfg.repo}/actions/workflows/{cfg.workflow}/dispatches"
    headers = {
        "Authorization": f"Bearer {cfg.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body: dict[str, Any] = {
        "ref": ref.strip() or cfg.default_ref,
        "inputs": {"environment": (environment or "production").strip()[:120]},
    }
    with httpx.Client(timeout=45.0) as client:
        r = client.post(url, headers=headers, json=body)
        r.raise_for_status()
