"""Keep synchronous document/database I/O off the ASGI event loop."""
import asyncio
import functools
import inspect
from starlette.concurrency import run_in_threadpool


async def run_document_io(operation, /, *args, **kwargs):
    # Do not abandon the worker on cancellation: dependency teardown must not
    # close the request Session while the document operation is still using it.
    def run():
        return asyncio.run(operation(*args, **kwargs))
    return await run_in_threadpool(run)


def document_io(operation):
    """Offload a complete service without concurrently sharing its Session.

    Request bodies must be consumed on the ASGI loop before using this helper.
    Per-operation async HTTP clients belong to the worker's private event loop.
    """
    @functools.wraps(operation)
    async def wrapped(*args, **kwargs):
        return await run_document_io(operation, *args, **kwargs)
    wrapped.__signature__ = inspect.signature(operation, eval_str=True)
    return wrapped
