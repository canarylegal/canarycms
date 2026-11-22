"""Radicale 3.1 rights adapter: live GUI grants, no persistent authorization cache."""
from contextvars import ContextVar
import hashlib
import hmac
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
from radicale.rights import BaseRights

request_context = ContextVar('canary_dav_request', default=None)


class Rights(BaseRights):
    def authorization(self, user, path):
        context = request_context.get()
        if not user or context is None:
            return ''
        method, request_path = context
        try:
            key = Path(self.configuration.get('auth', 'htpasswd_filename')).read_bytes()
            if not key.strip():
                return ''
            body = json.dumps({'user': user, 'path': path, 'method': method,
                               'request_path': request_path, 'timestamp': time.time()}).encode()
            signature = hmac.new(hashlib.sha256(b'canary-caldav-rights-v1\0' + key).digest(), body, hashlib.sha256).hexdigest()
            request = Request('http://backend:8000/internal/caldav/rights', data=body,
                              headers={'Content-Type': 'application/json', 'X-Canary-DAV-Signature': signature})
            with urlopen(request, timeout=3) as response:
                result = json.loads(response.read(256))['rights']
            return result if isinstance(result, str) and all(c in 'RWrw' for c in result) else ''
        except Exception:
            # Backend outage, malformed response and credential rotation all deny.
            return ''
