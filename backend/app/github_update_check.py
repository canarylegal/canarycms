"""Compare running build to GitHub (prefer latest *release*, not floating main)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.build_metadata import effective_build_commit_for_update_check
from app.github_deploy import (
    configured_github_deploy_ref,
    is_latest_release_ref,
    load_github_repo_for_api,
)
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


def resolve_compare_ref(
    client: httpx.Client,
    *,
    owner: str,
    repo: str,
    configured_ref: str,
    headers: dict[str, str],
) -> tuple[str, str | None, dict[str, Any] | None]:
    """Resolve env REF to a commits-API ref.

    Returns ``(api_ref, note, latest_release_json_or_none)``.
    For ``latest-release``, ``api_ref`` is the latest release tag name.
    """
    if not is_latest_release_ref(configured_ref):
        return configured_ref, None, None
    rel = client.get(f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest", headers=headers)
    if rel.status_code != 200:
        return (
            "main",
            f"Could not read latest GitHub release ({rel.status_code}); comparing to main instead.",
            None,
        )
    rj = rel.json()
    tag = str(rj.get("tag_name") or "").strip()
    if not tag:
        return "main", "Latest GitHub release had no tag_name; comparing to main instead.", rj
    return tag, None, rj


def build_update_check_payload() -> dict[str, Any]:
    """Data for ``GET /admin/deploy/update-check`` (no secrets)."""
    prompt = (os.getenv("CANARY_UPDATE_PROMPT_ON_LOGIN") or "1").strip().lower() not in ("0", "false", "no", "off")
    current = effective_build_commit_for_update_check() or "unknown"

    # Always false: in-app Compose updates were removed (notify-only Admin → Deploy).
    compose_deploy = compose_update_configured()
    configured_ref = configured_github_deploy_ref()
    base: dict[str, Any] = {
        "github_repo_configured": False,
        "deploy_trigger_configured": compose_deploy,
        "compose_update_enabled": compose_deploy,
        "compose_git_reset_enabled": False,
        "compose_git_ref": configured_ref,
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

    owner, repo, _configured = ident
    base["github_repo_configured"] = True

    headers = _api_headers()
    timeout = httpx.Timeout(20.0, connect=10.0)

    with httpx.Client(timeout=timeout) as client:
        ref, resolve_note, latest_rel = resolve_compare_ref(
            client,
            owner=owner,
            repo=repo,
            configured_ref=configured_ref,
            headers=headers,
        )
        if resolve_note:
            base["note"] = resolve_note
        base["remote_ref"] = ref
        base["compose_git_ref"] = ref

        tip = client.get(f"{GITHUB_API}/repos/{owner}/{repo}/commits/{ref}", headers=headers)
        if tip.status_code != 200:
            msg = f"Could not read ref tip for {ref!r} ({tip.status_code})."
            if tip.status_code in (401, 403, 404):
                msg += (
                    " Update checks use the public GitHub API only; private or unavailable repositories are not supported."
                )
            prev = (base.get("note") or "").strip()
            base["note"] = f"{prev} {msg}".strip() if prev else msg
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
            cmp = client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/compare/{current}...{remote_sha}",
                headers=headers,
            )
            if cmp.status_code == 200:
                cj = cmp.json()
                ahead_by = int(cj.get("ahead_by") or 0)
                base["update_available"] = ahead_by > 0
                if base["update_available"]:
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
                elif int(cj.get("behind_by") or 0) > 0:
                    prev = (base.get("note") or "").strip()
                    tail = (
                        f"This deployment ({_short_sha(current)}) is ahead of GitHub {_short_sha(remote_sha)} "
                        "with unpublished local commits. Push from your server checkout, or reset the host git "
                        "tree to the remote ref before rebuilding (see docs/DEPLOYMENT.md)."
                    )
                    base["note"] = f"{prev} {tail}".strip() if prev else tail
            else:
                base["update_available"] = not _same_commit(current, remote_sha)
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
                    base["update_available"] = False
                base["note"] = f"{prev} {tail}".strip() if prev else tail

        # Latest release notes (reuse body if we already fetched for latest-release).
        rj = latest_rel
        if rj is None:
            rel = client.get(f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest", headers=headers)
            if rel.status_code == 200:
                rj = rel.json()
        if isinstance(rj, dict):
            base["latest_release_tag"] = rj.get("tag_name")
            base["latest_release_name"] = rj.get("name")
            body = rj.get("body")
            if isinstance(body, str) and body.strip():
                base["latest_release_body"] = body.strip()[:8000]

    return base
