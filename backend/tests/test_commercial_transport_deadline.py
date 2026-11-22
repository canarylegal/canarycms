"""Real local TLS and cancellation tests; no external endpoints or credentials."""
import asyncio
import datetime
import ssl
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from app import commercial_transport as transport


@pytest.fixture
def tls_server(tmp_path, monkeypatch):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"localhost")])
    now=datetime.datetime.now(datetime.timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1))
        .not_valid_after(now+datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]),critical=False)
        .sign(key,hashes.SHA256()))
    certfile=tmp_path/"cert.pem";keyfile=tmp_path/"key.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            try:
                if self.path == '/headers': time.sleep(1)
                self.send_response(200)
                self.send_header('Content-Length', '11')
                self.end_headers()
                for byte in b'{"ok":true}':
                    if self.path == '/drip': time.sleep(.08)
                    self.wfile.write(bytes([byte])); self.wfile.flush()
            except (OSError, ssl.SSLError): pass
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile, keyfile)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    original = httpx.AsyncClient
    def local_ca(**kwargs):
        assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False
        return original(verify=ssl.create_default_context(cafile=str(certfile)), **kwargs)
    monkeypatch.setattr(transport.httpx, 'AsyncClient', local_ca)
    monkeypatch.setattr(transport, 'TOTAL_TIMEOUT_SECONDS', .4)
    try:
        yield transport.Transport(f'https://localhost:{server.server_port}'), requests
    finally:
        server.shutdown(); server.server_close(); thread.join(2)


def test_local_https_success(tls_server):
    client, requests = tls_server
    assert client.request('GET', '/fast') == {'ok': True}
    assert requests == ['/fast']


@pytest.mark.parametrize('path', ['/drip', '/headers'])
def test_total_deadline_includes_headers_and_slow_body(tls_server, path):
    client, requests = tls_server
    started = time.monotonic()
    with pytest.raises(transport.ConnectionError, match='service_unavailable'):
        client.request('GET', path, secret='synthetic-secret')
    assert time.monotonic() - started < .8
    assert requests == [path]  # No automatic retry after an uncertain response.


def test_deadline_closes_async_stream(monkeypatch):
    closed = threading.Event()
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                yield b' '
                await asyncio.sleep(.01)
        async def aclose(self): closed.set()
    original = httpx.AsyncClient
    monkeypatch.setattr(transport.httpx, 'AsyncClient', lambda **kw: original(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=SlowBody())), **kw))
    monkeypatch.setattr(transport, 'TOTAL_TIMEOUT_SECONDS', .1)
    with pytest.raises(transport.ConnectionError, match='service_unavailable'):
        transport.Transport('https://synthetic.test').request('GET', '/')
    assert closed.wait(2)


def test_stuck_resolver_is_bounded_and_capacity_recovers(monkeypatch):
    # asyncio.run waits for its resolver executor on shutdown. The synchronous
    # caller must still return on time, and stuck workers must not grow unbounded.
    release, entered = threading.Event(), threading.Event()
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(transport, '_REQUEST_SLOTS', slots)
    monkeypatch.setattr(transport, 'TOTAL_TIMEOUT_SECONDS', .1)
    async def unresolved(*args):
        def resolver():
            entered.set(); release.wait(5)
        await asyncio.get_running_loop().run_in_executor(None, resolver)
        return {'ok': True}
    monkeypatch.setattr(transport.Transport, '_exchange', unresolved)
    client = transport.Transport('https://synthetic.test')
    try:
        started = time.monotonic()
        with pytest.raises(transport.ConnectionError, match='service_unavailable'): client.request('GET', '/')
        assert entered.is_set() and time.monotonic() - started < .5
        started = time.monotonic()
        with pytest.raises(transport.ConnectionError, match='service_unavailable'): client.request('GET', '/')
        assert time.monotonic() - started < .1
    finally:
        release.set()
    assert slots.acquire(timeout=2)
    slots.release()


@pytest.mark.parametrize('payload,code', [(b'[]', 'service_unavailable'), (b'not-json', 'service_unavailable'),
    (b'x' * (transport.MAX_BYTES + 1), 'invalid_response')])
def test_invalid_and_oversized_responses_are_sanitized(monkeypatch, payload, code):
    original = httpx.AsyncClient
    monkeypatch.setattr(transport.httpx, 'AsyncClient', lambda **kw: original(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload)), **kw))
    with pytest.raises(transport.ConnectionError) as error:
        transport.Transport('https://synthetic.test').request('GET', '/')
    assert str(error.value) == code


def test_certificate_hostname_is_verified(tls_server):
    client, requests = tls_server
    bad_host = transport.Transport(client.origin.replace('localhost', '127.0.0.1'))
    with pytest.raises(transport.ConnectionError, match='service_unavailable'):
        bad_host.request('GET', '/fast')
    assert requests == []


def test_stalled_tls_handshake_is_bounded(monkeypatch):
    import socket
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0)); listener.listen(1)
    release, accepted = threading.Event(), threading.Event()
    def serve():
        with listener.accept()[0]:
            accepted.set(); release.wait(2)
    thread = threading.Thread(target=serve, daemon=True); thread.start()
    monkeypatch.setattr(transport, 'TOTAL_TIMEOUT_SECONDS', .2)
    try:
        started = time.monotonic()
        with pytest.raises(transport.ConnectionError, match='service_unavailable'):
            transport.Transport(f'https://127.0.0.1:{listener.getsockname()[1]}').request('GET', '/')
        assert accepted.is_set() and time.monotonic() - started < .6
    finally:
        release.set(); listener.close(); thread.join(2)
