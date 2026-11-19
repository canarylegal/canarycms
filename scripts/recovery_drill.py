#!/usr/bin/env python3
"""Restore a paired release backup into NEW volumes on an internal-only network."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import subprocess
import tarfile
import time

PG = 'postgres:16.6@sha256:557fea37a744d5f4c8faab304b0a90858b53ab119735a88c131fd19dab802f36'
OFFICE = 'onlyoffice/documentserver:9.0.3@sha256:6cf2c2727696954fb25f3f6061f195a6b1a366e1e7c66a3d53fb004322544d21'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def archive_manifest(path):
    files = {}
    with tarfile.open(path) as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or not (member.isfile() or member.isdir()):
                raise RuntimeError(f'Unsafe archive member: {member.name}')
            if member.isfile():
                normalized = str(name)
                if normalized in files:
                    raise RuntimeError('Duplicate archive member: ' + normalized)
                with archive.extractfile(member) as stream:
                    files[normalized] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return files


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')
    path.chmod(0o600)


def output(command):
    return subprocess.check_output(command, text=True).strip()


def build_config(project, images, encryption_key, commercial, module_path="/commercial/module"):
    env = {
        'POSTGRES_USER': 'canary', 'POSTGRES_DB': 'canary_recovery', 'POSTGRES_HOST': 'db',
        'POSTGRES_PASSWORD': secrets.token_urlsafe(32), 'JWT_SECRET': secrets.token_urlsafe(48),
        'DATA_ENCRYPTION_KEY': encryption_key, 'FILES_ROOT': '/data/files',
        'MASTER_ADMIN_LOGIN': 'recovery-' + secrets.token_hex(8),
        'MASTER_ADMIN_PASSWORD': secrets.token_urlsafe(32), 'MASTER_ADMIN_REQUIRE_2FA': 'false',
        'CANARY_BACKGROUND_JOBS_ENABLED': '0', 'CANARY_UPDATE_PROMPT_ON_LOGIN': '0',
        'CANARY_RUNTIME_COMMIT_FROM_COMPOSE_REPO': '0', 'CANARY_PUBLIC_URL': 'http://frontend',
        'CANARY_CORS_ORIGINS': 'http://frontend', 'ONLYOFFICE_JWT_SECRET': secrets.token_urlsafe(32),
        'ONLYOFFICE_DS_PUBLIC_URL': 'http://frontend/office-ds', 'ONLYOFFICE_DS_INTERNAL_URL': 'http://onlyoffice',
        'ONLYOFFICE_APP_URL_INTERNAL': 'http://backend:8000', 'ONLYOFFICE_CALLBACK_REQUIRE_JWT': '1',
    }
    mounts = [{'type': 'volume', 'source': 'files', 'target': '/data/files'}]
    if commercial:
        mounts.append({'type': 'bind', 'source': str(commercial), 'target': '/commercial', 'read_only': True})
        if not (module_path == '/commercial' or module_path.startswith('/commercial/')) or '..' in PurePosixPath(module_path).parts:
            raise RuntimeError('Optional module path must be within the copied /commercial package.')
        env.update(COMMERCIAL_MODULE_DIR=module_path, COMMERCIAL_PACKAGE_DIR='/commercial')
    config = {'name': project, 'services': {
        'db': {'image': PG, 'environment': {k: env[k] for k in ('POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB')},
               'volumes': ['database:/var/lib/postgresql/data'],
               'healthcheck': {'test': ['CMD-SHELL', 'pg_isready -U canary -d canary_recovery'], 'interval': '2s', 'timeout': '3s', 'retries': 40}},
        'backend': {'image': images['backend'], 'environment': env, 'volumes': mounts,
                    # First boot must NOT migrate a restored database implicitly.
                    'command': ['uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'],
                    'healthcheck': {'test': ['CMD', 'python', '-c', "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"], 'interval': '3s', 'timeout': '5s', 'retries': 40, 'start_period': '30s'}},
        'onlyoffice': {'image': OFFICE, 'environment': {'JWT_ENABLED': 'true', 'JWT_SECRET': env['ONLYOFFICE_JWT_SECRET'], 'JWT_IN_BODY': 'true', 'ALLOW_PRIVATE_IP_ADDRESS': 'true', 'ALLOW_META_IP_ADDRESS': 'false'},
                       'healthcheck': {'test': ['CMD-SHELL', 'curl -fsS http://localhost/healthcheck | grep -q true'], 'interval': '5s', 'timeout': '5s', 'retries': 90, 'start_period': '90s'}},
        'frontend': {'image': images['frontend'], 'depends_on': {'backend': {'condition': 'service_healthy'}, 'onlyoffice': {'condition': 'service_healthy'}}},
    }, 'networks': {'default': {'internal': True}}, 'volumes': {
        'database': {'name': project + '-database'}, 'files': {'name': project + '-files'},
    }}
    assert_isolated(config, project)
    return config


def assert_isolated(config, project):
    if not project.startswith('canaryrestore-') or not config['networks']['default'].get('internal'):
        raise RuntimeError('Recovery must use a new canaryrestore project and an internal network.')
    for service in config['services'].values():
        if any(service.get(k) for k in ('ports', 'container_name', 'network_mode', 'privileged', 'external_links')):
            raise RuntimeError('Recovery services may not expose ports or share host/container namespaces.')
    for volume in config['volumes'].values():
        if not volume['name'].startswith(project + '-') or volume.get('external'):
            raise RuntimeError('Recovery volumes must be owned by the new project.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', required=True, type=Path)
    parser.add_argument('--state', required=True, type=Path, help='NEW private directory; must not already exist')
    parser.add_argument('--backend-image', required=True, help='Matching backup image, or explicitly tested candidate')
    parser.add_argument('--frontend-image', required=True)
    parser.add_argument('--commercial-source', type=Path, help='Optional package source to copy into the private drill directory')
    args = parser.parse_args()
    os.umask(0o077)
    started = time.monotonic()
    release = args.release.resolve()
    expected = json.loads((release / 'checksums.json').read_text())
    for name in ('database.dump', 'files.tar'):
        if digest(release / name) != expected[name]:
            raise RuntimeError('Backup checksum mismatch: ' + name)
    files = archive_manifest(release / 'files.tar')
    previous = json.loads((release / 'previous.json').read_text())
    env = previous['services']['backend']['environment']
    if not env.get('DATA_ENCRYPTION_KEY'):
        raise RuntimeError('The backup deployment encryption key is required.')
    if (env.get('COMMERCIAL_MODULE_DIR') or env.get('COMMERCIAL_PACKAGE_DIR')) and not args.commercial_source:
        raise RuntimeError('This backup used an optional package. Supply its matching source snapshot.')
    state = args.state.resolve()
    if state.exists() or state == release or state in release.parents or release in state.parents:
        raise RuntimeError('State must be a new directory, separate from the backup.')
    if args.commercial_source:
        source = args.commercial_source.resolve()
        if not source.is_dir() or source == state or source in state.parents:
            raise RuntimeError('Optional package must be a directory outside the new state directory ancestry.')
    state.mkdir(parents=True, mode=0o700)
    project = 'canaryrestore-' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + '-' + secrets.token_hex(3)
    for suffix in ('database', 'files'):
        if subprocess.run(['docker', 'volume', 'inspect', project + '-' + suffix], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            raise RuntimeError('Refusing to restore over an existing volume.')
    images = {name: output(['docker', 'image', 'inspect', image, '--format', '{{.Id}}']) for name, image in [('backend', args.backend_image), ('frontend', args.frontend_image)]}
    for name in ('database.dump', 'files.tar'):
        shutil.copyfile(release / name, state / name)
        if digest(state / name) != expected[name]:
            raise RuntimeError('Backup changed during copy.')
    commercial = None
    if args.commercial_source:
        commercial = state / 'commercial'
        shutil.copytree(args.commercial_source.resolve(), commercial, ignore=shutil.ignore_patterns('.git', '.env', '.env.*', '__pycache__', 'node_modules'))
    config = build_config(project, images, env['DATA_ENCRYPTION_KEY'], commercial, env.get('COMMERCIAL_MODULE_DIR') or '/commercial/module')
    write_json(state / 'compose.json', config)
    write_json(state / 'files-manifest.json', files)
    report = {'project': project, 'source_release': str(release), 'backup_checksums': expected,
              'images': images, 'file_count': len(files), 'phase': 'prepared',
              'optional_package_files': {str(p.relative_to(commercial)): digest(p) for p in commercial.rglob('*') if p.is_file()} if commercial else {}}
    write_json(state / 'recovery.json', report)
    compose = ['docker', 'compose', '-p', project, '-f', str(state / 'compose.json')]
    with (state / 'restore.log').open('w') as log:
        def run(command, **kwargs):
            return subprocess.run(command, check=True, stdout=log, stderr=log, **kwargs)
        run(compose + ['up', '-d', '--wait', '--wait-timeout', '120', 'db'])
        with (state / 'database.dump').open('rb') as src:
            run(compose + ['exec', '-T', 'db', 'pg_restore', '--exit-on-error', '--single-transaction', '--no-owner', '--no-privileges', '-U', 'canary', '-d', 'canary_recovery'], stdin=src)
        with (state / 'files.tar').open('rb') as src:
            run(compose + ['run', '--rm', '--no-deps', '-T', '--entrypoint', 'tar', 'backend', '-xpf', '-', '-C', '/data/files'], stdin=src)
        verify = "import pathlib,hashlib,json; p=pathlib.Path('/data/files'); print(json.dumps({str(f.relative_to(p)):hashlib.file_digest(f.open('rb'),'sha256').hexdigest() for f in p.rglob('*') if f.is_file()}))"
        actual = json.loads(output(compose + ['run', '--rm', '--no-deps', '-T', '--entrypoint', 'python', 'backend', '-c', verify]))
        if actual != files:
            raise RuntimeError('Restored file manifest differs from backup.')
        inventory_script = Path(__file__).resolve().parents[1] / 'backend/scripts/recovery_inventory.py'
        inventory = json.loads(output(compose + ['run', '--rm', '--no-deps', '-T', '-e', 'PYTHONPATH=/app', '-v', f'{inventory_script}:/tmp/recovery_inventory.py:ro', 'backend', 'python', '/tmp/recovery_inventory.py']))
        if inventory['missing_file_ids']:
            write_json(state / 'inventory-before.json', inventory)
            raise RuntimeError('Restored database references missing files; inspect the private inventory.')
        write_json(state / 'inventory-before.json', inventory)
        report.update(phase='data_restored', data_restore_seconds=round(time.monotonic() - started, 2))
        write_json(state / 'recovery.json', report)
        run(compose + ['up', '-d', '--wait', '--wait-timeout', '600'])
        network = json.loads(output(['docker', 'network', 'inspect', project + '_default']))[0]
        if not network['Internal']:
            raise RuntimeError('Recovery network is not internal.')
    report.update(phase='healthy', ready_seconds=round(time.monotonic() - started, 2))
    write_json(state / 'recovery.json', report)
    print(f'Restored {len(files)} files with matching hashes. Isolated project: {project}')
    print(f'Healthy after {report["ready_seconds"]} seconds. Private state: {state}')
    print('Run authenticated verification next. No live services or volumes were used.')


if __name__ == '__main__':
    main()
