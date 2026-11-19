"""Bounded dependency probes. Results contain codes, never connection details."""
from __future__ import annotations
import json
import os
import shutil
import tempfile
from urllib.request import urlopen
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool


def database_probe():
    from app.db import DATABASE_URL
    options = {} if DATABASE_URL.startswith('sqlite') else {
        'connect_timeout': 2, 'options': '-c statement_timeout=2000'}
    engine = create_engine(DATABASE_URL, poolclass=NullPool, connect_args=options)
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return {'status': 'ok'}
    finally:
        engine.dispose()


def storage_probe():
    from app.file_storage import FILES_ROOT
    # Do not create a missing mount: an empty directory must not conceal missing storage.
    if not FILES_ROOT.is_dir():
        return {'status': 'failed', 'code': 'storage_missing'}
    with tempfile.TemporaryFile(dir=FILES_ROOT, prefix='.canary-health-') as stream:
        stream.write(b'canary-health'); stream.flush(); os.fsync(stream.fileno())
        stream.seek(0)
        if stream.read() != b'canary-health':
            return {'status': 'failed', 'code': 'storage_readback_failed'}
    free = shutil.disk_usage(FILES_ROOT).free
    minimum = max(0, int(os.getenv('CANARY_STORAGE_MIN_FREE_BYTES', str(512 * 1024 * 1024))))
    return {'status': 'ok' if free >= minimum else 'failed',
            'code': 'storage_available' if free >= minimum else 'storage_low_space', 'free_bytes': free}


def office_probe():
    url = os.getenv('ONLYOFFICE_DS_INTERNAL_URL', '').rstrip('/')
    if not url:
        return {'status': 'not_configured'}
    with urlopen(url + '/healthcheck', timeout=3) as response:
        healthy = response.status == 200 and response.read(32).strip() == b'true'
    return {'status': 'ok' if healthy else 'failed', 'code': 'onlyoffice_healthcheck'}


def probe(name, function):
    try:
        return function()
    except Exception:
        return {'status': 'failed', 'code': name + '_unavailable'}


def health_snapshot(include_office=True):
    checks = {'database': probe('database', database_probe), 'storage': probe('storage', storage_probe)}
    ready = all(item['status'] == 'ok' for item in checks.values())
    if include_office:
        checks['onlyoffice'] = probe('onlyoffice', office_probe)
    degraded = any(item['status'] == 'failed' for item in checks.values())
    return {'status': 'ready' if not degraded else 'degraded', 'ready': ready, 'checks': checks}


if __name__ == '__main__':
    print(json.dumps(health_snapshot()))
