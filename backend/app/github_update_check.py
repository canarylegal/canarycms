"""Compare running build to GitHub default branch; gather release / commit notes for admin UI."""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.build_metadata import effective_build_commit_for_update_check
from app.github_deploy import load_github_repo_for_api
from app.local_compose_update import compose_update_configured

GITHUB_API = "https://api.github.com"


def _api_headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _short_sha(sha: str) -> str:
    s = (sha or "").strip().lower()
    if len(s) >= 7:
        return s[:7]
    return s


def _same_commit(a: str, b: str) -> bool:
    if not a or not b or a == "unknown" or b == "unknown":
        return False
    if a == b:
        return True
    return _short_sha(a) == _short_sha(b)


def build_update_check_payload() -> dict[str, Any]:
    """Data for ``GET /admin/deploy/update-check`` (no secrets)."""
    prompt = (os.getenv("CANARY_UPDATE_PROMPT_ON_LOGIN") or "1").strip().lower() not in ("0", "false", "no", "off")
    current = effective_build_commit_for_update_check() or "unknown"

    compose_deploy = compose_update_configured()
    base: dict[str, Any] = {
        "github_repo_configured": False,
        "deploy_trigger_configured": compose_deploy,
        "compose_update_enabled": compose_deploy,
        "prompt_enabled": prompt,
        "current_commit": current,
        "current_commit_short": _short_sha(current) if current != "unknown" else "unknown",
        "remote_ref": "",
        "remote_commit": "",
        "remote_commit_short": "",
        "update_available": False,
        "build_commit_unknown": current == "unknown",
        "compare_html_url": None,
        "latest_release_tag": None,
        "latest_release_name": None,
        "latest_release_body": None,
        "commit_messages": [],
        "note": None,
    }

    ident = load_github_repo_for_api()
    if ident is None:
        base["note"] = "Set CANARY_GITHUB_DEPLOY_OWNER and CANARY_GITHUB_DEPLOY_REPO to check for updates."
        return base

    owner, repo, ref = ident
    base["github_repo_configured"] = True
    base["remote_ref"] = ref

    headers = _api_headers()
    timeout = httpx.Timeout(20.0, connect=10.0)

    with httpx.Client(timeout=timeout) as client:
        tip = client.get(f"{GITHUB_API}/repos/{owner}/{repo}/commits/{ref}", headers=headers)
        if tip.status_code != 200:
            msg = f"Could not read branch tip ({tip.status_code})."
            if tip.status_code in (401, 403, 404):
                msg += (
                    " Update checks use the public GitHub API only; private or unavailable repositories are not supported."
                )
            base["note"] = msg
            return base
        tip_j = tip.json()
        remote_sha = str(tip_j.get("sha") or "")
        if not remote_sha:
            base["note"] = "GitHub returned an empty commit SHA."
            return base
        base["remote_commit"] = remote_sha
        base["remote_commit_short"] = _short_sha(remote_sha)

        if current == "unknown":
            base["update_available"] = False
            extra = (
                "Rebuild the backend image with build-arg GIT_COMMIT (see docker-compose.yml) "
                "to compare this deployment to GitHub."
            )
            prev = (base.get("note") or "").strip()
            base["note"] = f"{prev} {extra}".strip() if prev else extra
        else:
            base["update_available"] = not _same_commit(current, remote_sha)

        # Latest release (optional human notes)
        rel = client.get(f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest", headers=headers)
        if rel.status_code == 200:
            rj = rel.json()
            base["latest_release_tag"] = rj.get("tag_name")
            base["latest_release_name"] = rj.get("name")
            body = rj.get("body")
            if isinstance(body, str) and body.strip():
                base["latest_release_body"] = body.strip()[:8000]

        if base["update_available"] and current != "unknown":
            cmp = client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/compare/{current}...{remote_sha}",
                headers=headers,
            )
            if cmp.status_code == 200:
                cj = cmp.json()
                base["compare_html_url"] = cj.get("html_url")
                msgs: list[str] = []
                for c in cj.get("commits") or []:
                    if len(msgs) >= 40:
                        break
                    commit = (c or {}).get("commit") or {}
                    msg = commit.get("message")
                    if isinstance(msg, str) and msg.strip():
                        msgs.append(msg.strip().split("\n", 1)[0].strip()[:500])
                base["commit_messages"] = msgs
            else:
                prev = (base.get("note") or "").strip()
                tail = f"Could not load commit list (compare {cmp.status_code})."
                tip_cur = client.get(
                    f"{GITHUB_API}/repos/{owner}/{repo}/commits/{current}",
                    headers=headers,
                )
                if tip_cur.status_code != 200:
                    tail = (
                        f"{tail} This deployment reports {_short_sha(current)}, which GitHub does not expose on "
                        f"{owner}/{repo}. The update banner compares this install to that repository's {ref} tip "
                        f"({_short_sha(remote_sha)}). Point CANARY_GITHUB_DEPLOY_OWNER / REPO / REF at the remote "
                        "that contains this commit, or push your checkout to the configured repository."
                    )
                base["note"] = f"{prev} {tail}".strip() if prev else tail

    return base
