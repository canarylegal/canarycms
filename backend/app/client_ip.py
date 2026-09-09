"""Client IP resolution.

Prefer ``request.client.host``, which Uvicorn's ``ProxyHeadersMiddleware`` already
rewrites from ``X-Forwarded-For`` when the peer is in ``CANARY_PROXY_TRUSTED_HOSTS``.
Do not re-parse ``X-Forwarded-For`` here — that invites client spoofing.
"""

from __future__ import annotations

from fastapi import Request


def client_ip_from_request(request: Request) -> str | None:
    if request.client and request.client.host:
        return request.client.host
    return None
