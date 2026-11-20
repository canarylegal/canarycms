"""Privacy-preserving HTTP diagnostics; no bodies, raw URLs or exception messages."""
import json
import logging
import time
import uuid

logger = logging.getLogger('canary.http')


class RequestDiagnosticsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex  # Never trust an attacker-supplied correlation header.
        scope.setdefault('state', {})['request_id'] = request_id
        started = time.monotonic()
        status = 500
        response_started = False
        error_type = None
        error_location = None

        async def tagged_send(message):
            nonlocal status, response_started
            if message['type'] == 'http.response.start':
                response_started = True
                status = message['status']
                message = dict(message)
                headers = [(k, v) for k, v in message.get('headers', []) if k.lower() != b'x-request-id']
                message['headers'] = headers + [(b'x-request-id', request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, tagged_send)
        except Exception as exc:
            error_type = type(exc).__name__
            trace = exc.__traceback__
            while trace and trace.tb_next:
                trace = trace.tb_next
            if trace:
                error_location = {'module': trace.tb_frame.f_globals.get('__name__', '<unknown>'),
                                  'function': trace.tb_frame.f_code.co_name, 'line': trace.tb_lineno}
            status = 500
            if response_started:
                # A partial download cannot be converted to a successful response.
                # Raise a sanitized error without retaining the sensitive exception chain.
                raise RuntimeError('Response interrupted; request_id=' + request_id) from None
            body = json.dumps({'detail': 'Internal server error', 'request_id': request_id}).encode()
            await tagged_send({'type': 'http.response.start', 'status': 500,
                               'headers': [(b'content-type', b'application/json'), (b'cache-control', b'no-store')]})
            await send({'type': 'http.response.body', 'body': body})
        finally:
            route = scope.get('route')
            record = {'event': 'http_request', 'request_id': request_id,
                      'method': scope['method'], 'route': getattr(route, 'path', '<unmatched>'),
                      'status': status, 'duration_ms': round((time.monotonic() - started) * 1000, 2)}
            if error_type:
                record['error_type'] = error_type
                record['error_location'] = error_location
            logger.log(logging.ERROR if status >= 500 else logging.INFO, json.dumps(record))


def configure_request_logging():
    # Replace raw URL access logs (query strings can contain document/session tokens).
    logging.getLogger('uvicorn.access').disabled = True
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
    logger.propagate = False
