#!/usr/bin/env python3
"""Optional, manually invoked monitoring delivery. Never imported by Core startup."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid

CHECKS = ('application', 'database', 'storage', 'onlyoffice', 'public_access', 'backup', 'recovery')
MAX_QUEUE = 100
MAX_STATE = 512 * 1024
MAX_INPUT = 64 * 1024
FRESH_SECONDS = 600
RETRY_CAP = 300


def read_file(path, limit, private=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Expected regular file')
        if private and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError('Expected owner-only file')
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Input too large')
    return raw


def settings(path):
    if path is None or not Path(path).exists():
        return None
    config = json.loads(read_file(path, MAX_INPUT))
    if not isinstance(config, dict):
        raise ValueError('Invalid settings')
    if config.get('enabled', False) is False:
        return None
    if config.get('enabled') is not True:
        raise ValueError('enabled must be boolean')
    read_file(path, MAX_INPUT, private=True)
    url = urlsplit(config['endpoint'])
    if (url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment
            or any(c.isspace() for c in config['endpoint'])):
        raise ValueError('Expected credential-free HTTPS endpoint')
    if url.port is not None and not 1 <= url.port <= 65535:
        raise ValueError('Invalid port')
    if str(uuid.UUID(config['installation_id'])) != config['installation_id']:
        raise ValueError('Expected canonical installation UUID')
    for key in ('state_dir', 'report_file', 'token_file'):
        if not Path(config[key]).is_absolute():
            raise ValueError('Expected absolute paths')
    if config.get('ca_file') and not Path(config['ca_file']).is_absolute():
        raise ValueError('Expected absolute CA path')
    required = config.get('expected_checks', ['application','database','storage','onlyoffice','public_access'])
    if not isinstance(required, list) or not required or len(set(required)) != len(required) or not set(required) <= set(CHECKS):
        raise ValueError('Invalid expected checks')
    config['expected_checks'] = required
    # Check locally before any delivery; never print the credential or endpoint.
    token(config)
    return config


def token(config):
    value = read_file(config['token_file'], 4096, private=True).decode().strip()
    if not re.fullmatch(r'[A-Za-z0-9._~+/-]{16,4096}={0,2}', value):
        raise ValueError('Invalid bearer credential')
    return value


def binding(config):
    raw = json.dumps([config['endpoint'], config['installation_id']], separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def observation(config, now):
    source_time = None
    valid = False
    statuses = {name: 'disabled' if name not in config['expected_checks'] else 'unknown' for name in CHECKS}
    try:
        report = json.loads(read_file(config['report_file'], MAX_INPUT))
        stamp = datetime.fromisoformat(report['checked_at'])
        source_time = int(stamp.timestamp())
        if source_time < 0:
            source_time = None; raise ValueError('Invalid timestamp')
        checks = report['checks']
        if stamp.tzinfo is None or not 0 <= now - source_time <= FRESH_SECONDS or not isinstance(checks, dict):
            raise ValueError('Invalid source')
        for value in checks.values():
            if not isinstance(value, dict) or value.get('status') not in ('ok','failed','not_configured'):
                raise ValueError('Invalid source check')
        valid = True
        for name in config['expected_checks']:
            value = checks.get(name, {}).get('status')
            if name == 'application' and value is None and 'database' in checks and 'storage' in checks:
                value = 'ok'  # The local application probe executed and returned its dependency results.
            statuses[name] = {'ok':'up','failed':'down','not_configured':'not_configured'}.get(value, 'unknown')
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        pass
    statuses['monitor_source'] = 'up' if valid else 'down'
    return {'source_observed_at': source_time, 'checks': statuses}


def new_state(config):
    return {'version':1, 'binding':binding(config), 'stream_id':str(uuid.uuid4()), 'sequence':0,
            'outbox':[], 'last_source_time':0, 'last_observation':None, 'last_delivery_at':None, 'last_error':None}


def validate_event(event):
    common = {'schema_version','kind','event_id','installation_id','stream_id','created_at'}
    extra = {'sequence','source_observed_at','checks'} if event.get('kind') == 'observation' else {'last_observation_sequence'}
    if set(event) != common | extra or type(event['schema_version']) is not int or event['schema_version'] != 1 or event['kind'] not in ('observation','heartbeat'):
        raise ValueError('Invalid event shape')
    for key in ('event_id','installation_id','stream_id'):
        if str(uuid.UUID(event[key])) != event[key]:raise ValueError('Invalid event identity')
    for key in ('created_at','sequence' if event['kind']=='observation' else 'last_observation_sequence'):
        if type(event[key]) is not int or event[key] < (0 if key == 'created_at' else 1):raise ValueError('Invalid event number')
    if event['kind']=='observation':
        if event['source_observed_at'] is not None and (type(event['source_observed_at']) is not int or event['source_observed_at'] < 0):
            raise ValueError('Invalid observation time')
        if set(event['checks']) != set(CHECKS) | {'monitor_source'} or any(v not in ('up','down','unknown','disabled','not_configured') for v in event['checks'].values()):
            raise ValueError('Invalid event checks')
    return event


def validate_state(state, config):
    if type(state['version']) is not int or state['version'] != 1 or state['binding'] != binding(config):
        raise ValueError('State belongs to a different destination or installation')
    uuid.UUID(state['stream_id'])
    if type(state['sequence']) is not int or state['sequence'] < 0:
        raise ValueError('Invalid sequence')
    if not isinstance(state['outbox'], list) or len(state['outbox']) > MAX_QUEUE:
        raise ValueError('Invalid outbox')
    last = 0
    for item in state['outbox']:
        event = validate_event(item['event'])
        if (event['kind'] != 'observation' or event['installation_id'] != config['installation_id']
                or event['stream_id'] != state['stream_id'] or not last < event['sequence'] <= state['sequence']):
            raise ValueError('Invalid queued observation')
        uuid.UUID(event['event_id']); last = event['sequence']
        if type(item['attempts']) is not int or item['attempts'] < 0 or type(item['next_attempt']) is not int:
            raise ValueError('Invalid retry state')
    return state


def save(directory, state):
    raw = json.dumps(state, separators=(',', ':')).encode()
    if len(raw) > MAX_STATE:
        raise ValueError('State too large')
    temporary = directory / 'state.tmp'  # One bounded scratch file, reused after an interrupted save.
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('Expected regular scratch file')
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, directory/'state.json')
        fd = os.open(directory, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(config):
    directory = Path(config['state_dir'])
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Expected private state directory')
    fd = os.open(directory/'lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = directory/'state.json'
        state = validate_state(json.loads(read_file(path, MAX_STATE, private=True)), config) if path.exists() or path.is_symlink() else new_state(config)
        yield directory, state
    finally:
        os.close(fd)


def envelope(config, state, kind, now):
    return {'schema_version':1, 'kind':kind, 'event_id':str(uuid.uuid4()),
            'installation_id':config['installation_id'], 'stream_id':state['stream_id'], 'created_at':now}


def send_http(config, event):
    """Child-only HTTPS operation. Parent deadline also bounds DNS and stalled reads."""
    url = urlsplit(config['endpoint'])
    context = ssl.create_default_context(cafile=config.get('ca_file'))
    connection = http.client.HTTPSConnection(url.hostname, url.port or 443, timeout=3, context=context)
    try:
        body = json.dumps(validate_event(event), separators=(',', ':')).encode()
        connection.request('POST', url.path or '/', body=body, headers={
            'Authorization':'Bearer '+token(config), 'Content-Type':'application/json',
            'Idempotency-Key':event['event_id'], 'User-Agent':'Canary-Monitoring/1'})
        response = connection.getresponse()  # No redirects or ambient HTTP proxy support.
        retry = response.getheader('Retry-After', '')
        return {'status':response.status, 'retry_after':min(RETRY_CAP, int(retry)) if retry.isascii() and retry.isdigit() and len(retry) <= 8 else 0}
    finally:
        connection.close()  # Response bodies are deliberately not read or logged.


def transport(config, event):
    try:
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), '_send'],
            input=json.dumps({'config':config,'event':event}), text=True, capture_output=True, timeout=6, check=True)
        return json.loads(completed.stdout)
    except (subprocess.SubprocessError, ValueError, OSError):
        return {'status':0, 'retry_after':0}


def run(config, now=None, sender=transport):
    now = int(time.time()) if now is None else now
    started = time.monotonic()
    clock = lambda: now + int(time.monotonic() - started)
    current = observation(config, now)
    with locked(config) as (directory, state):
        if current['checks']['monitor_source'] == 'up':
            if current['source_observed_at'] < state['last_source_time']:
                current['checks'] = {name: 'unknown' if name in config['expected_checks'] else 'disabled' for name in CHECKS}
                current['checks']['monitor_source'] = 'down'
            else:
                state['last_source_time'] = current['source_observed_at']
        full = False
        if current != state['last_observation']:
            if len(state['outbox']) == MAX_QUEUE:
                full = True; state['last_error'] = 'queue_full'
            else:
                state['sequence'] += 1
                event = envelope(config, state, 'observation', now)
                event.update(sequence=state['sequence'], **current)
                state['outbox'].append({'event':event,'attempts':0,'next_attempt':now})
                state['last_observation'] = current
        save(directory, state)  # Durable before any external side effect.
        delivered = 0
        for _ in range(5):
            if not state['outbox'] or state['outbox'][0]['next_attempt'] > now:
                break
            item = state['outbox'][0]
            result = sender(config, item['event'])
            if 200 <= result['status'] < 300:
                state['outbox'].pop(0); delivered += 1
                state['last_delivery_at'] = clock(); state['last_error'] = None
            else:
                item['attempts'] += 1
                delay = min(RETRY_CAP, 30 * 2 ** min(item['attempts']-1, 4))
                if result['status'] in (429,503):delay = max(delay, min(RETRY_CAP, max(0, result.get('retry_after',0))))
                item['next_attempt'] = clock() + delay
                state['last_error'] = 'authentication_rejected' if result['status'] in (401,403) else 'delivery_failed'
            save(directory, state)
            if state['last_error']: break
        heartbeat = False
        # Heartbeats are fresh, never replayed from a delayed observation queue.
        fresh = current['checks']['monitor_source'] == 'up' and 0 <= clock() - current['source_observed_at'] <= FRESH_SECONDS
        if not full and not state['outbox'] and fresh:
            event = envelope(config, state, 'heartbeat', clock())
            event['last_observation_sequence'] = state['sequence']
            result = sender(config, event)
            heartbeat = 200 <= result['status'] < 300
            state['last_error'] = None if heartbeat else 'heartbeat_failed'
            save(directory, state)
        if full:
            state['last_error'] = 'queue_full'; save(directory, state)
        ok = not full and not state['outbox'] and heartbeat
        return {'status':'ok' if ok else 'degraded', 'queued':len(state['outbox']),
                'delivered':delivered, 'heartbeat_delivered':heartbeat,
                'source_fresh':fresh, 'error':state['last_error']}


def main():
    if len(sys.argv) == 2 and sys.argv[1] == '_send':
        try:
            raw = sys.stdin.buffer.read(MAX_INPUT + 1)
            if len(raw) > MAX_INPUT:raise ValueError('Oversize request')
            request = json.loads(raw)
            print(json.dumps(send_http(request['config'], request['event'])))
        except Exception:
            print(json.dumps({'status':0,'retry_after':0}))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, help='Absent/missing/disabled config performs no delivery')
    args = parser.parse_args()
    try:
        config = settings(args.config)
        result = run(config) if config else {'status':'disabled'}
        print(json.dumps(result))
        return 0 if result['status'] in ('ok','disabled') else 1
    except Exception:
        # Never leak endpoint, credential, raw report or exception text to the journal.
        print(json.dumps({'status':'failed','error':'monitoring_delivery_failed'}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
