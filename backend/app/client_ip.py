"""Client IP behind reverse proxies (Cloudflare, nginx, etc.)."""

from __future__ import annotations

from fastapi import Request


def client_ip_from_request(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    if request.client:
        return request.client.host
    return None
