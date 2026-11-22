"""Bounded HTTPS transport. No redirects, proxies, retries or raw remote errors."""
from __future__ import annotations
import json
import os
from urllib.parse import urlsplit
import httpx

VERSION = "1"
MAX_BYTES = 1024 * 1024


class ConnectionError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def configured_origin() -> str:
    if os.getenv("CANARY_COMMERCIAL_SERVICE_ENABLED") != "1":
        raise ConnectionError("disabled")
    raw = os.getenv("CANARY_COMMERCIAL_SERVICE_ORIGIN", "")
    try:
        u = urlsplit(raw)
        valid = (u.scheme == "https" and u.hostname and not u.username and not u.password
                 and u.port in (None, 443) and u.path in ("", "/") and not u.query and not u.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ConnectionError("invalid_service_origin")
    # Operator-controlled, never accepted from browser, adapter or remote response.
    return raw.rstrip("/")


class Transport:
    def __init__(self, origin: str):
        self.origin = origin

    def request(self, method: str, path: str, body: dict | None = None, secret: str | None = None) -> dict:
        headers = {"Accept": "application/json", "X-Canary-Contract": VERSION}
        if secret:
            headers["Authorization"] = "Bearer " + secret
        try:
            with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
                with client.stream(method, self.origin + path, json=body, headers=headers) as response:
                    if response.status_code != 200:
                        raise ConnectionError("remote_rejected")
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_BYTES:
                            raise ConnectionError("invalid_response")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (httpx.HTTPError, ValueError):
            raise ConnectionError("service_unavailable") from None
