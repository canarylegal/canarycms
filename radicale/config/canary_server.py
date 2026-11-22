"""Supply request context to the pinned Radicale rights adapter."""
from radicale import server
from radicale.__main__ import run
from radicale.app import Application
from canary_rights import request_context


class CanaryApplication(Application):
    def __call__(self, environ, start_response):
        token = request_context.set((environ.get('REQUEST_METHOD', ''), environ.get('PATH_INFO', '')))
        try:
            yield from super().__call__(environ, start_response)
        finally:
            request_context.reset(token)


if __name__ == '__main__':
    server.Application = CanaryApplication
    run()
