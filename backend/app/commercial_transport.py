"""Bounded HTTPS transport. No redirects, proxies, retries or raw remote errors."""
from __future__ import annotations
import asyncio
import json
import threading
import time
import os
from urllib.parse import urlsplit
import httpx

VERSION = "1"
MAX_BYTES = 1024 * 1024
TOTAL_TIMEOUT_SECONDS = 20.0
# Bound outstanding workers, including a platform resolver that ignores cancellation.
_REQUEST_SLOTS = threading.BoundedSemaphore(4)


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

    async def _exchange(self, method, path, body, secret, deadline):
        headers = {"Accept": "application/json", "X-Canary-Contract": VERSION}
        if secret:
            headers["Authorization"] = "Bearer " + secret
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ConnectionError("service_unavailable")
        async with httpx.AsyncClient(timeout=remaining, follow_redirects=False, trust_env=False) as client:
            async with client.stream(method, self.origin + path, json=body, headers=headers) as response:
                if response.status_code != 200:
                    raise ConnectionError("remote_rejected")
                raw = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    if len(raw) + len(chunk) > MAX_BYTES:
                        raise ConnectionError("invalid_response")
                    raw.extend(chunk)
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError()
        return data

    def request(self, method: str, path: str, body: dict | None = None, secret: str | None = None) -> dict:
        """One attempt with a wall-clock deadline covering DNS through response parsing.

        Async cancellation closes network streams. The bounded daemon bridge also
        limits the synchronous caller's wait if platform DNS cannot be cancelled.
        It never owns a DB session and never retries an ambiguous operation.
        """
        deadline = time.monotonic() + TOTAL_TIMEOUT_SECONDS
        slots = _REQUEST_SLOTS
        if not slots.acquire(blocking=False):
            raise ConnectionError("service_unavailable")
        done = threading.Event()
        state = {}

        async def run():
            state['loop'] = asyncio.get_running_loop()
            state['task'] = asyncio.current_task()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ConnectionError("service_unavailable")
            return await asyncio.wait_for(self._exchange(method, path, body, secret, deadline), remaining)

        def worker():
            try:
                state['result'] = asyncio.run(run())
            except ConnectionError as error:
                state['error'] = error.code
            except (Exception, asyncio.CancelledError):
                # Never expose remote bodies, URLs, credentials or resolver errors.
                state['error'] = 'service_unavailable'
            finally:
                slots.release()
                done.set()

        try:
            threading.Thread(target=worker, name='commercial-request', daemon=True).start()
        except Exception:
            slots.release()
            raise ConnectionError('service_unavailable') from None
        if not done.wait(max(0.0, deadline - time.monotonic())):
            loop, task = state.get('loop'), state.get('task')
            if loop is not None and task is not None:
                try:
                    loop.call_soon_threadsafe(task.cancel)
                except RuntimeError:  # Worker already finished and closed its loop.
                    pass
            raise ConnectionError('service_unavailable')
        if 'error' in state:
            raise ConnectionError(state['error'])
        return state['result']
