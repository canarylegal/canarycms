"""Bound multipart ingress before parsing, including chunked or encoded requests."""
import re
from tempfile import SpooledTemporaryFile
import anyio
from starlette.responses import JSONResponse
from app.upload_limits import max_upload_bytes

UPLOAD_PATH = re.compile(r"^/(?:cases/[^/]+/files|portal/grants/[^/]+/files|portal/forms/[^/]+/upload|precedents)/?$")
MULTIPART_ALLOWANCE = 1024 * 1024


class UploadBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or not UPLOAD_PATH.fullmatch(scope["path"]):
            return await self.app(scope, receive, send)
        limit = max_upload_bytes() + MULTIPART_ALLOWANCE
        lengths = [v for k, v in scope.get("headers", []) if k.lower() == b"content-length"]
        if lengths:
            try:
                if len(lengths) != 1 or not lengths[0].isdigit():
                    raise ValueError()
                declared = int(lengths[0])
            except ValueError:
                return await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(scope, receive, send)
            if declared > limit:
                return await JSONResponse({"detail": "Upload request exceeds size limit"}, status_code=413)(scope, receive, send)
        # Stage only the bounded body, spilling after 1 MiB. Never dispatch oversized
        # bodies to the multipart parser. Disk I/O stays off the event loop.
        with SpooledTemporaryFile(max_size=MULTIPART_ALLOWANCE) as body:
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > limit:
                    return await JSONResponse({"detail": "Upload request exceeds size limit"}, status_code=413)(scope, receive, send)
                await anyio.to_thread.run_sync(body.write, chunk)
                if not message.get("more_body", False):
                    break
            await anyio.to_thread.run_sync(body.seek, 0)
            remaining = size
            empty_sent = size > 0

            async def replay():
                nonlocal remaining, empty_sent
                if remaining <= 0:
                    if not empty_sent:
                        empty_sent = True
                        return {"type": "http.request", "body": b"", "more_body": False}
                    return await receive()
                chunk = await anyio.to_thread.run_sync(body.read, 64 * 1024)
                remaining -= len(chunk)
                return {"type": "http.request", "body": chunk, "more_body": remaining > 0}

            await self.app(scope, replay, send)
