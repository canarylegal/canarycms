#!/usr/bin/env python3
"""Repeatable upgrades of an existing Compose deployment. Never removes volumes."""
from __future__ import annotations

from contextlib import contextmanager
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import urllib.request
from datetime import datetime, timezone


@contextmanager
def operation_lock(project):
    """Serialize backups/deployments for this project and Docker operator account."""
    key = hashlib.sha256(project.encode()).hexdigest()[:24]
    path = Path('/tmp') / f'canary-operation-{os.getuid()}-{key}.lock'
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        if os.fstat(lock.fileno()).st_uid != os.getuid():
            raise RuntimeError('Operation lock has an unexpected owner.')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def output(args):
    return subprocess.check_output(args, text=True).strip()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')
    path.chmod(0o600)


def compose(config, *args):
    return ['docker', 'compose', '-f', str(config), '--profile', 'prod', *args]


def inspect(container):
    return json.loads(output(['docker', 'inspect', container]))[0]


def schema_fingerprint(db):
    # Also covers optional-package tables, not just the core Alembic revision.
    raw = output(['docker', 'exec', db, 'sh', '-ec',
                  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --schema-only --no-owner --no-privileges'])
    stable = '\n'.join(line for line in raw.splitlines()
                       if not line.startswith(('\\restrict ', '\\unrestrict ', '--')))
    return hashlib.sha256(stable.encode()).hexdigest()


def dependents(services, roots):
    selected = set(roots)
    while True:
        extra = {name for name, service in services.items()
                 if service.get('network_mode', '').removeprefix('service:') in selected}
        if extra <= selected:
            return sorted(selected)
        selected |= extra


def data_identity(info):
    return sorted((m['Destination'], m['Type'], m.get('Name') or m['Source'])
                  for m in info['Mounts'])


def configured_data_identity(config, service):
    result = []
    for mount in config['services'][service].get('volumes', []):
        kind = mount['type']
        source = mount['source']
        if kind == 'volume':
            source = config['volumes'][source]['name']
        elif kind != 'bind':
            raise RuntimeError('Only bind mounts and named volumes are supported.')
        result.append((mount['target'], kind, source))
    return sorted(result)


def ensure_source(source, sha=None):
    if output(['git', '-C', str(source), 'status', '--porcelain']):
        raise RuntimeError('Commit or stash source changes before preparing a deployment.')
    actual = output(['git', '-C', str(source), 'rev-parse', 'HEAD'])
    if sha and actual != sha:
        raise RuntimeError('Source commit changed after preparation. Prepare a new release.')
    return actual


def prepare(args, state):
    source = Path(args.source).resolve()
    if state == source or source in state.parents:
        raise RuntimeError('Deployment state must live outside the source checkout.')
    sha = ensure_source(source)
    config = Path(args.config).resolve()
    current = json.loads(output(compose(config, 'config', '--format', 'json')))
    services = current['services']
    if any(name not in services for name in ('backend', 'frontend', 'db')):
        raise RuntimeError('Expected existing backend, frontend and managed db services.')
    active = {}
    for name in services:
        ids = output(compose(config, 'ps', '-q', name)).splitlines()
        if ids:
            if len(ids) != 1:
                raise RuntimeError('This updater supports one container per service.')
            active[name] = inspect(ids[0])
    if any(name not in active for name in ('backend', 'frontend', 'db')):
        raise RuntimeError('Existing backend, frontend and db must be running before preparation.')
    targets = dependents(services, ['backend', 'frontend'])
    if any(name not in active for name in targets):
        raise RuntimeError('All frontend/backend network companions must already be running.')
    for name in ('db', 'backend'):
        if configured_data_identity(current, name) != data_identity(active[name]):
            raise RuntimeError(f'{name} configured data mounts differ from the running deployment. Resolve before preparing.')
    # Back up only the database actually used by this application; external DBs need their own updater.
    env = dict(item.split('=', 1) for item in active['backend']['Config']['Env'])
    db_env = dict(item.split('=', 1) for item in active['db']['Config']['Env'])
    if env.get('DATABASE_URL') or env.get('POSTGRES_HOST', 'db') != 'db' or env.get('POSTGRES_DB') != db_env.get('POSTGRES_DB'):
        raise RuntimeError('External/explicit DATABASE_URL is not supported: verify a database-specific backup procedure first.')
    if not any(m['Destination'] == '/data/files' for m in active['backend']['Mounts']):
        raise RuntimeError('Expected persistent /data/files storage.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    release = state / f'{stamp}-{sha[:12]}'
    release.mkdir(mode=0o700)
    previous = copy.deepcopy(current)
    target = copy.deepcopy(current)
    for name, info in active.items():
        previous['services'][name]['image'] = info['Image']
        target['services'][name]['image'] = info['Image']
    for name in ('backend', 'frontend'):
        target['services'][name]['build']['context'] = str(source / name)
        target['services'][name]['image'] = f"{current['name']}-{name}:release-{stamp.lower()}"
    target['services']['backend']['build'].setdefault('args', {})['GIT_COMMIT'] = sha
    # The deployed image, not a mounted checkout or stale environment override, owns build identity.
    target['services']['backend'].setdefault('environment', {}).update({
        'CANARY_BUILD_COMMIT_OVERRIDE': '', 'CANARY_RUNTIME_COMMIT_FROM_COMPOSE_REPO': '0',
    })
    save(release / 'previous.json', previous)
    save(release / 'compose.json', target)
    manifest = {'commit': sha, 'source': str(source), 'url': args.url.rstrip('/'),
                'project': current['name'], 'targets': targets, 'phase': 'prepared',
                'containers': {n: i['Id'] for n, i in active.items()},
                'data': {n: data_identity(active[n]) for n in ('db', 'backend')},
                'previous_commit': None}
    try:
        manifest['previous_commit'] = health(args.url)['build_commit']
    except Exception as exc:
        raise RuntimeError(f'Existing public health endpoint must be reachable before preparation: {exc}') from exc
    save(release / 'manifest.json', manifest)
    print(f'Prepared {release}\nCommit: {sha}\nProject: {current["name"]}\nServices: {", ".join(targets)}')
    print('Configuration contains secrets; keep the release directory private.')


def public_request(url):
    return urllib.request.Request(url, headers={'User-Agent': 'Canary-Deployment/1.0'})


def health(url):
    with urllib.request.urlopen(public_request(url.rstrip('/') + '/api/health'), timeout=10) as response:
        return json.load(response)


def verify(config, manifest, expected, timeout=180):
    deadline = time.monotonic() + timeout
    last = 'not ready'
    while time.monotonic() < deadline:
        try:
            for service in manifest['targets']:
                container = output(compose(config, 'ps', '-q', service))
                info = inspect(container)
                if not info['State']['Running'] or info['State'].get('Health', {}).get('Status', 'healthy') != 'healthy':
                    raise RuntimeError(f'{service} is not healthy')
            for service, identity in manifest['data'].items():
                info = inspect(output(compose(config, 'ps', '-q', service)))
                if data_identity(info) != [tuple(x) for x in identity]:
                    raise RuntimeError(f'{service} data mounts changed')
            h = health(manifest['url'])
            if h.get('status') != 'ok' or h.get('build_commit') != expected:
                raise RuntimeError('Public endpoint is not serving the expected commit')
            with urllib.request.urlopen(public_request(manifest['url']), timeout=10) as response:
                if response.status != 200 or b'id="root"' not in response.read():
                    raise RuntimeError('Frontend app shell is unavailable')
            return
        except Exception as exc:
            last = str(exc)
            time.sleep(3)
    raise RuntimeError(f'Verification timed out: {last}')


def backup(release, manifest, stderr=None):
    db = manifest['containers']['db']
    manifest['schema_before'] = schema_fingerprint(db)
    with (release / 'database.dump').open('wb') as dest:
        subprocess.run(['docker', 'exec', db, 'sh', '-ec',
                        'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'], stdout=dest, stderr=stderr, check=True)
    with (release / 'database.dump').open('rb') as src:
        subprocess.run(['docker', 'exec', '-i', db, 'pg_restore', '--list'], stdin=src, stdout=subprocess.DEVNULL, stderr=stderr, check=True)
    with (release / 'files.tar').open('wb') as dest:
        previous = json.loads((release / 'previous.json').read_text())
        subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--volumes-from',
                        manifest['containers']['backend'] + ':ro', '--entrypoint', 'tar',
                        previous['services']['backend']['image'], '-C', '/data/files', '-cf', '-', '.'], stdout=dest, stderr=stderr, check=True)
    with tarfile.open(release / 'files.tar') as archive:
        for member in archive:
            if member.isfile():
                stream = archive.extractfile(member)
                while stream.read(1024 * 1024):
                    pass
    checksums = {}
    for name in ('database.dump', 'files.tar'):
        with (release / name).open('rb') as file:
            checksums[name] = hashlib.file_digest(file, 'sha256').hexdigest()
    save(release / 'checksums.json', checksums)
    save(release / 'manifest.json', manifest)


def rollback(release, manifest):
    if not manifest.get('schema_before'):
        raise RuntimeError('No verified pre-upgrade database snapshot exists.')
    db = output(compose(release / 'previous.json', 'ps', '-q', 'db'))
    if schema_fingerprint(db) != manifest['schema_before']:
        raise RuntimeError('Schema changed: automatic code rollback is unsafe. Use the documented coordinated database/files restore procedure. Backups are retained.')
    run(compose(release / 'previous.json', 'up', '-d', '--no-build', '--no-deps', '--force-recreate', *manifest['targets']))
    verify(release / 'previous.json', manifest, manifest['previous_commit'])
    manifest['phase'] = 'rolled_back'
    save(release / 'manifest.json', manifest)


def apply(release, manifest):
    if manifest['phase'] != 'prepared':
        raise RuntimeError('Release already attempted. Prepare a new release instead of overwriting backups.')
    ensure_source(Path(manifest['source']), manifest['commit'])
    for name, identifier in manifest['containers'].items():
        current = output(compose(release / 'previous.json', 'ps', '-q', name))
        if current != identifier:
            raise RuntimeError('Deployment changed after preparation; prepare again.')
    config = release / 'compose.json'
    with (release / 'build.log').open('w') as log:
        run(compose(config, 'build', 'backend', 'frontend'), stdout=log, stderr=subprocess.STDOUT)
    ensure_source(Path(manifest['source']), manifest['commit'])
    target = json.loads(config.read_text())
    for name in ('backend', 'frontend'):
        image = target['services'][name]['image']
        target['services'][name]['image'] = output(['docker', 'image', 'inspect', image, '--format', '{{.Id}}'])
    save(config, target)
    for name, identifier in manifest['containers'].items():
        if output(compose(release / 'previous.json', 'ps', '-q', name)) != identifier:
            raise RuntimeError('Deployment changed during build; prepare again.')
    manifest['phase'] = 'backing_up'
    save(release / 'manifest.json', manifest)
    try:
        # Quiesce all app entry points; leave PostgreSQL and persistent volumes running.
        run(compose(release / 'previous.json', 'stop', *manifest['targets']))
        backup(release, manifest)
    except BaseException:
        run(compose(release / 'previous.json', 'start', *manifest['targets']))
        raise
    try:
        manifest['phase'] = 'starting'
        save(release / 'manifest.json', manifest)
        run(compose(config, 'up', '-d', '--no-build', '--no-deps', '--force-recreate', *manifest['targets']))
        verify(config, manifest, manifest['commit'])
    except BaseException:
        manifest['phase'] = 'failed'
        save(release / 'manifest.json', manifest)
        rollback(release, manifest)
        raise
    manifest['phase'] = 'verified'
    save(release / 'manifest.json', manifest)
    print(f'Verified {manifest["commit"]} at {manifest["url"]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', required=True, type=Path, help='Private directory outside the checkout')
    sub = parser.add_subparsers(dest='command', required=True)
    prepare_parser = sub.add_parser('prepare')
    prepare_parser.add_argument('--source', required=True)
    prepare_parser.add_argument('--config', required=True, help='Existing Compose file, including resolved overlays')
    prepare_parser.add_argument('--url', required=True)
    for command in ('apply', 'rollback', 'status'):
        sub.add_parser(command).add_argument('release', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    state = args.state_dir.resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'prepare':
            prepare(args, state)
        else:
            release = args.release.resolve()
            if release.parent != state:
                raise RuntimeError('Release must be a direct child of the state directory.')
            manifest = json.loads((release / 'manifest.json').read_text())
            if args.command == 'status':
                print(json.dumps({k: manifest.get(k) for k in ('commit', 'source', 'project', 'url', 'targets', 'phase')}, indent=2))
                run(compose(release / ('previous.json' if manifest['phase'] == 'rolled_back' else 'compose.json'), 'ps'))
            else:
                with operation_lock(manifest['project']):
                    if args.command == 'apply':
                        apply(release, manifest)
                    else:
                        rollback(release, manifest)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, BlockingIOError) as error:
        print(f'Deployment failed: {error}', file=sys.stderr)
        sys.exit(1)
