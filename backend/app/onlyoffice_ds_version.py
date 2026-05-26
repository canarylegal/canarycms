"""Detect installed ONLYOFFICE Document Server major version (for PDF editor config)."""

from __future__ import annotations

import logging
import os
import time

import httpx
import jwt as pyjwt

log = logging.getLogger(__name__)

_CACHE_TTL_S = 3600.0
_cached_major: int | None = None
_cached_at: float = 0.0


def _parse_major(version: str) -> int | None:
    parts = (version or "").strip().split(".")
    if not parts or not parts[0].isdigit():
        return None
    return int(parts[0])


def _command_request_body(inner: dict[str, str]) -> dict[str, str]:
    secret = (os.getenv("ONLYOFFICE_JWT_SECRET") or "").strip()
    if not secret:
        return inner
    token = pyjwt.encode(inner, secret, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return {"token": token}


def _probe_onlyoffice_ds_major() -> int | None:
    base = (os.getenv("ONLYOFFICE_DS_INTERNAL_URL") or "http://onlyoffice").strip().rstrip("/")
    inner = {"c": "version"}
    body = _command_request_body(inner)
    for path in ("/command", "/coauthoring/CommandService.ashx"):
        url = f"{base}{path}"
        try:
            with httpx.Client(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
                r = client.post(url, json=body)
            if r.status_code != 200:
                continue
            data = r.json()
            if isinstance(data, dict) and data.get("error") not in (0, None, "0"):
                continue
            ver = str((data or {}).get("version") or "")
            major = _parse_major(ver)
            if major is not None:
                log.info("onlyoffice_ds_version: probed %s → %s (major %s)", url, ver, major)
                return major
        except Exception as e:
            log.debug("onlyoffice_ds_version: probe %s failed: %s", url, e)
    return None


def onlyoffice_ds_major() -> int:
    """Major DS version for feature gating (env override, else cached probe, else 7)."""
    global _cached_major, _cached_at

    raw = (os.getenv("ONLYOFFICE_DS_MAJOR") or "").strip().lower()
    if raw and raw not in ("auto", ""):
        try:
            return int(raw)
        except ValueError:
            log.warning("onlyoffice_ds_version: invalid ONLYOFFICE_DS_MAJOR=%r", raw)

    now = time.monotonic()
    if _cached_major is not None and (now - _cached_at) < _CACHE_TTL_S:
        return _cached_major

    probed = _probe_onlyoffice_ds_major()
    major = probed if probed is not None else 7
    if probed is None:
        log.warning(
            "onlyoffice_ds_version: could not probe Document Server; assuming major=%s "
            "(set ONLYOFFICE_DS_MAJOR explicitly if wrong)",
            major,
        )
    _cached_major = major
    _cached_at = now
    return major


def invalidate_onlyoffice_ds_version_cache() -> None:
    global _cached_major, _cached_at
    _cached_major = None
    _cached_at = 0.0
