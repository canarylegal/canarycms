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
import signal
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


def recovery_keys(env):
    """Keep data recoverable without keeping the original session-signing key active."""
    encryption_key = env.get('DATA_ENCRYPTION_KEY')
    if not encryption_key:
        if not env.get('JWT_SECRET'):
            raise RuntimeError('The backup deployment encryption key is required.')
        import base64
        encryption_key = base64.urlsafe_b64encode(hashlib.sha256(env['JWT_SECRET'].encode()).digest()).decode()
    return encryption_key, env.get('DATA_LEGACY_JWT_SECRET') or env.get('JWT_SECRET')


def build_config(project, images, encryption_key, commercial, module_path="/commercial/module", legacy_jwt_secret=None):
    env = {
        'POSTGRES_USER': 'canary', 'POSTGRES_DB': 'canary_recovery', 'POSTGRES_HOST': 'db',
        'POSTGRES_PASSWORD': secrets.token_urlsafe(32), 'JWT_SECRET': secrets.token_urlsafe(48),
        'DATA_ENCRYPTION_KEY': encryption_key, 'FILES_ROOT': '/data/files',
        'MASTER_ADMIN_LOGIN': 'recovery-' + secrets.token_hex(8),
        'MASTER_ADMIN_PASSWORD': secrets.token_urlsafe(32), 'MASTER_ADMIN_REQUIRE_2FA': 'false',
        'CANARY_BACKGROUND_JOBS_ENABLED': '0', 'CANARY_COMMERCIAL_SERVICE_ENABLED': '0', 'CANARY_UPDATE_PROMPT_ON_LOGIN': '0',
        'CANARY_RUNTIME_COMMIT_FROM_COMPOSE_REPO': '0', 'CANARY_PUBLIC_URL': 'http://frontend',
        'CANARY_CORS_ORIGINS': 'http://frontend', 'ONLYOFFICE_JWT_SECRET': secrets.token_urlsafe(32),
        'ONLYOFFICE_DS_PUBLIC_URL': 'http://frontend/office-ds', 'ONLYOFFICE_DS_INTERNAL_URL': 'http://onlyoffice',
        'ONLYOFFICE_APP_URL_INTERNAL': 'http://backend:8000', 'ONLYOFFICE_CALLBACK_REQUIRE_JWT': '1',
    }
    if legacy_jwt_secret:
        env['DATA_LEGACY_JWT_SECRET'] = legacy_jwt_secret
    mounts = [{'type': 'volume', 'source': 'files', 'target': '/data/files'}]
    if commercial:
        mounts.append({'type': 'bind', 'source': str(commercial), 'target': '/commercial', 'read_only': True})
        if not (module_path == '/commercial' or module_path.startswith('/commercial/')) or '..' in PurePosixPath(module_path).parts:
            raise RuntimeError('Optional module path must be within the copied /commercial package.')
        env.update(COMMERCIAL_MODULE_DIR=module_path, COMMERCIAL_PACKAGE_DIR='/commercial')
    config = {'name': project, 'services': {
        'db': {'image': images.get('db', PG), 'environment': {k: env[k] for k in ('POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB')},
               'volumes': ['database:/var/lib/postgresql/data'],
               'healthcheck': {'test': ['CMD-SHELL', 'pg_isready -U canary -d canary_recovery'], 'interval': '2s', 'timeout': '3s', 'retries': 40}},
        'backend': {'image': images['backend'], 'environment': env, 'volumes': mounts,
                    # First boot must NOT migrate a restored database implicitly.
                    'command': ['uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'],
                    'healthcheck': {'test': ['CMD', 'python', '-c', "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"], 'interval': '3s', 'timeout': '5s', 'retries': 40, 'start_period': '30s'}},
        'onlyoffice': {'image': images.get('onlyoffice', OFFICE), 'environment': {'PLUGINS_ENABLED': 'false', 'JWT_ENABLED': 'true', 'JWT_SECRET': env['ONLYOFFICE_JWT_SECRET'], 'JWT_IN_BODY': 'true', 'ALLOW_PRIVATE_IP_ADDRESS': 'true', 'ALLOW_META_IP_ADDRESS': 'false'},
                       'healthcheck': {'test': ['CMD-SHELL', "pgrep -f '^tail -f /var/log/onlyoffice/documentserver/' >/dev/null && curl -fsS http://localhost/healthcheck | grep -q true"], 'interval': '5s', 'timeout': '5s', 'retries': 90, 'start_period': '90s'}},
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


def validate_bundle(release, expected):
    required = {'database.dump', 'files.tar', 'previous.json', 'inventory.json', 'images.tar', 'recovery-bundle.json'}
    if not required.issubset(expected):
        raise RuntimeError('Complete recovery bundle is missing required artifacts.')
    if not json.loads((release / 'inventory.json').read_text()).get('integrity', {}).get('ok'):
        raise RuntimeError('Complete recovery requires verified content and credential inventory.')
    bundle = json.loads((release / 'recovery-bundle.json').read_text())
    images = bundle.get('images', {})
    if bundle.get('version') != 1 or set(images) != {'backend', 'frontend', 'db', 'onlyoffice'}:
        raise RuntimeError('Complete recovery bundle has invalid image roles.')
    import re
    if any(not re.fullmatch(r'sha256:[0-9a-f]{64}', value) for value in images.values()):
        raise RuntimeError('Recovery images must be immutable IDs.')
    previous = json.loads((release / 'previous.json').read_text())
    backend = previous['services']['backend']
    targets = {m['target'] if isinstance(m, dict) else m.split(':')[1] for m in backend.get('volumes', [])}
    env = backend.get('environment', {})
    required_optional = set()
    if '/radicale-data' in targets: required_optional.add('calendars.tar')
    if '/commercial' in targets or env.get('COMMERCIAL_MODULE_DIR') or env.get('COMMERCIAL_PACKAGE_DIR'):
        required_optional.add('commercial.tar')
    if not required_optional.issubset(expected):
        raise RuntimeError('Complete recovery bundle is missing mounted data.')
    # Validate data archives before importing executable images or starting services.
    for name in ('files.tar', 'calendars.tar', 'commercial.tar'):
        if name in expected: archive_manifest(release / name)
    for role, image in images.items():
        if previous['services'][role]['image'] != image:
            raise RuntimeError('Bundle image does not match captured configuration.')
    return images


def archive_image_configs(path, images):
    """Resolve OCI/index IDs to portable config IDs without trusting daemon tags.

    Docker's containerd store reports manifest/index IDs; the classic store reports
    config IDs. A docker-save bundle can contain both representations.
    """
    with tarfile.open(path) as archive:
        members = {m.name: m for m in archive.getmembers()}
        def read(name):
            member = members[name]
            if not member.isfile() or member.size > 16 * 1024 * 1024:
                raise RuntimeError('Invalid image metadata.')
            raw = archive.extractfile(member).read()
            if name.startswith('blobs/sha256/') and hashlib.sha256(raw).hexdigest() != name.rsplit('/', 1)[-1]:
                raise RuntimeError('Image metadata digest mismatch.')
            return json.loads(raw)
        configs = set()
        for item in read('manifest.json'):
            name = item['Config']
            raw = archive.extractfile(members[name]).read()
            configs.add('sha256:' + hashlib.sha256(raw).hexdigest())
        def walk(digest, seen):
            if digest in configs: return {digest}
            if digest in seen: raise RuntimeError('Cyclic image metadata.')
            name = 'blobs/sha256/' + digest.removeprefix('sha256:')
            if name not in members: return set()  # Unexported architectures in an OCI index.
            node = read(name)
            if 'config' in node:
                candidate = node['config']['digest']
                return {candidate} if candidate in configs else set()
            found = set()
            for child in node.get('manifests', []):
                found.update(walk(child['digest'], seen | {digest}))
            return found
        result = {}
        for role, original in images.items():
            candidates = walk(original, set())
            if len(candidates) != 1:
                raise RuntimeError('Recovery image must contain one unambiguous platform.')
            result[role] = candidates.pop()
        return result


def load_bundle_images(release, expected, required=False):
    if not required and 'recovery-bundle.json' not in expected:
        return {}
    images = validate_bundle(release, expected)
    portable = archive_image_configs(release / 'images.tar', images)
    # Checksums were validated by the caller. Import only the trusted private bundle.
    subprocess.run(['docker', 'image', 'load', '-i', str(release / 'images.tar')],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    resolved = {}
    for role, original in images.items():
        for candidate in dict.fromkeys([original, portable[role]]):
            try:
                actual = subprocess.check_output(['docker', 'image', 'inspect', candidate, '--format', '{{.Id}}'],
                                                 text=True, stderr=subprocess.DEVNULL).strip()
            except subprocess.CalledProcessError:
                continue
            if actual == candidate:
                resolved[role] = actual
                break
        if role not in resolved:
            raise RuntimeError('Imported recovery image is missing or incorrect.')
    return resolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', required=True, type=Path)
    parser.add_argument('--state', required=True, type=Path, help='NEW private directory; must not already exist')
    parser.add_argument('--backend-image', help='Matching backup image, or explicitly tested candidate')
    parser.add_argument('--frontend-image')
    parser.add_argument('--require-complete', action='store_true', help='Require a self-contained bundle and import its verified images; never pull.')
    parser.add_argument('--commercial-source', type=Path, help='Optional package source to copy into the private drill directory')
    parser.add_argument('--verify', action='store_true', help='Run authenticated read/ledger checks in the clone')
    parser.add_argument('--cleanup', action='store_true', help='Remove only the new isolated project after success or failure')
    args = parser.parse_args()
    os.umask(0o077)
    def interrupted(signum, frame):
        raise InterruptedError('Recovery interrupted.')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    started = time.monotonic()
    release = args.release.resolve()
    expected = json.loads((release / 'checksums.json').read_text())
    for name in expected:
        if Path(name).name != name or (release / name).is_symlink():
            raise RuntimeError('Unsafe backup manifest filename.')
        if digest(release / name) != expected[name]:
            raise RuntimeError('Backup checksum mismatch: ' + name)
    files = archive_manifest(release / 'files.tar')
    previous = json.loads((release / 'previous.json').read_text())
    env = previous['services']['backend']['environment']
    encryption_key, legacy_jwt_secret = recovery_keys(env)
    if (env.get('COMMERCIAL_MODULE_DIR') or env.get('COMMERCIAL_PACKAGE_DIR')) and not args.commercial_source and not (release / 'commercial.tar').exists():
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
    bundled_images = load_bundle_images(release, expected, required=args.require_complete)
    if args.require_complete and args.commercial_source:
        raise RuntimeError('Complete recovery must use the bundled optional package.')
    for role, requested in [('backend', args.backend_image), ('frontend', args.frontend_image)]:
        if args.require_complete and requested and requested != json.loads((release / 'recovery-bundle.json').read_text())['images'][role]:
            raise RuntimeError('Complete recovery image override is not permitted.')
    requested_images = {name: override or bundled_images.get(name) for name, override in [('backend', args.backend_image), ('frontend', args.frontend_image)]}
    if args.require_complete:
        requested_images = {name: bundled_images[name] for name in ('backend', 'frontend')}
    if not all(requested_images.values()):
        raise RuntimeError('Images must be supplied or included in a complete recovery bundle.')
    images = {name: output(['docker', 'image', 'inspect', image, '--format', '{{.Id}}']) for name, image in requested_images.items()}
    images.update({k: v for k, v in bundled_images.items() if k in ('db', 'onlyoffice')})
    for name in ('database.dump', 'files.tar'):
        shutil.copyfile(release / name, state / name)
        if digest(state / name) != expected[name]:
            raise RuntimeError('Backup changed during copy.')
    commercial = None
    if args.commercial_source:
        commercial = state / 'commercial'
        shutil.copytree(args.commercial_source.resolve(), commercial, ignore=shutil.ignore_patterns('.git', '.env', '.env.*', '__pycache__', 'node_modules'))
    elif (release / 'commercial.tar').exists():
        archive_manifest(release / 'commercial.tar')
        commercial = state / 'commercial'
        commercial.mkdir(mode=0o700)
        with tarfile.open(release / 'commercial.tar') as archive:
            archive.extractall(commercial, filter='data')
    config = build_config(project, images, encryption_key, commercial, env.get('COMMERCIAL_MODULE_DIR') or '/commercial/module', legacy_jwt_secret)
    if (release / 'calendars.tar').exists():
        archive_manifest(release / 'calendars.tar')
        config['volumes']['calendars'] = {'name': project + '-calendars'}
        config['services']['backend']['volumes'].append({'type': 'volume', 'source': 'calendars', 'target': '/radicale-data'})
    assert_isolated(config, project)
    write_json(state / 'compose.json', config)
    write_json(state / 'files-manifest.json', files)
    report = {'project': project, 'source_release': str(release), 'backup_checksums': expected,
              'images': images, 'file_count': len(files), 'phase': 'prepared',
              'optional_package_files': {str(p.relative_to(commercial)): digest(p) for p in commercial.rglob('*') if p.is_file()} if commercial else {}}
    write_json(state / 'recovery.json', report)
    compose = ['docker', 'compose', '-p', project, '-f', str(state / 'compose.json')]
    try:
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
            if (release / 'calendars.tar').exists():
                with (release / 'calendars.tar').open('rb') as src:
                    run(compose + ['run', '--rm', '--no-deps', '-T', '--entrypoint', 'tar', 'backend', '-xpf', '-', '-C', '/radicale-data'], stdin=src)
                calendar_verify = verify.replace('/data/files', '/radicale-data')
                actual_calendars = json.loads(output(compose + ['run', '--rm', '--no-deps', '-T', '--entrypoint', 'python', 'backend', '-c', calendar_verify]))
                if actual_calendars != archive_manifest(release / 'calendars.tar'):
                    raise RuntimeError('Restored calendars differ from backup.')
            inventory_script = Path(__file__).resolve().parents[1] / 'backend/scripts/recovery_inventory.py'
            inventory = json.loads(output(compose + ['run', '--rm', '--no-deps', '-T', '-e', 'PYTHONPATH=/app', '-v', f'{inventory_script}:/tmp/recovery_inventory.py:ro', 'backend', 'python', '/tmp/recovery_inventory.py']))
            if inventory['missing_file_ids'] or not inventory.get('integrity', {}).get('ok', True):
                write_json(state / 'inventory-before.json', inventory)
                raise RuntimeError('Restored content or credential integrity failed; inspect the private inventory.')
            write_json(state / 'inventory-before.json', inventory)
            if (release / 'inventory.json').exists() and any(inventory.get(k) != v for k, v in json.loads((release / 'inventory.json').read_text()).items()):
                raise RuntimeError('Restored inventory differs from backup.')
            report['integrity'] = inventory.get('integrity', {})
            report['complete_bundle'] = args.require_complete
            report.update(phase='data_restored', data_restore_seconds=round(time.monotonic() - started, 2))
            write_json(state / 'recovery.json', report)
            run(compose + ['up', '-d', '--wait', '--wait-timeout', '600'])
            network = json.loads(output(['docker', 'network', 'inspect', project + '_default']))[0]
            if not network['Internal']:
                raise RuntimeError('Recovery network is not internal.')
        report.update(phase='healthy', ready_seconds=round(time.monotonic() - started, 2))
        write_json(state / 'recovery.json', report)
        if args.verify:
            script = Path(__file__).resolve().parents[1] / 'backend/scripts/verify_recovery_readonly.py'
            with script.open('rb') as source, (state / 'verification.log').open('w') as log:
                result = subprocess.check_output(compose + ['exec', '-T', 'backend', 'python', '-'], stdin=source, stderr=log, timeout=300)
            verification = json.loads(result)
            if verification.get('status') != 'verified':
                raise RuntimeError('Authenticated recovery check failed.')
            write_json(state / 'verification.json', verification)
            report.update(phase='verified', verification=verification, verified_seconds=round(time.monotonic() - started, 2))
            write_json(state / 'recovery.json', report)
        print(f'Restored {len(files)} files with matching hashes. Isolated project: {project}')
        print(f'Healthy after {report["ready_seconds"]} seconds. Private state: {state}')
        print('No live services or volumes were used.')
    except BaseException as exc:
        report.update(phase='failed', error_type=type(exc).__name__)
        write_json(state / 'recovery.json', report)
        raise
    finally:
        if args.cleanup:
            assert_isolated(config, project)
            result = subprocess.run(compose + ['down', '--volumes', '--remove-orphans'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
            report['cleanup'] = 'ok' if result.returncode == 0 else 'failed'
            write_json(state / 'recovery.json', report)
            if result.returncode:
                raise RuntimeError('Isolated recovery cleanup failed.')



if __name__ == '__main__':
    main()
