#!/usr/bin/env python3
"""Opt-in host operations. No timers are installed or enabled by this program."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import signal
import urllib.request
import uuid

import deploy
from recovery_drill import archive_manifest, digest, assert_isolated


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x') as stream:
            os.chmod(temporary, 0o600)
            json.dump(data, stream, indent=2); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path):
    return json.loads(Path(path).read_text())


def load_settings(path):
    config = read_json(path)
    for key in ('deployment_config', 'backup_dir', 'state_dir', 'public_url'):
        if not config.get(key):
            raise ValueError('Missing operations setting: ' + key)
    for key in ('deployment_config', 'backup_dir', 'state_dir'):
        if not Path(config[key]).is_absolute():
            raise ValueError('Operations paths must be absolute.')
    for key, default in [('max_backup_age_hours', 26), ('max_recovery_age_days', 35)]:
        if not 0 < float(config.get(key, default)) < float('inf'):
            raise ValueError('Freshness limits must be positive and finite.')
    if int(config.get('keep_backups', 14)) < 1:
        raise ValueError('At least one verified backup must be retained.')
    return config


def execute(command, **kwargs):
    # Command output stays in a private log, never in systemd's public summary.
    return subprocess.run(command, check=True, **kwargs)


def resolved(settings):
    return read_json_output(deploy.compose(settings['deployment_config'], 'config', '--format', 'json'))


def read_json_output(command):
    return json.loads(subprocess.check_output(command, stderr=subprocess.DEVNULL, text=True, timeout=45))


def private_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise RuntimeError('Operations directory must be private (0700) and not a symlink.')
    return path.resolve()


def inspect_running(config_path, services):
    active = {}
    for name in services:
        ids = deploy.output(deploy.compose(config_path, 'ps', '-q', name)).splitlines()
        if ids:
            if len(ids) != 1:
                raise RuntimeError('Expected one container per service.')
            active[name] = deploy.inspect(ids[0])
    return active


def validate_backup_destination(root, config, active):
    if any(name not in active for name in ('backend', 'frontend', 'db')):
        raise RuntimeError('Backend, frontend and managed database must be running.')
    for name in ('backend', 'db'):
        if name not in active or deploy.configured_data_identity(config, name) != deploy.data_identity(active[name]):
            raise RuntimeError('Active deployment storage does not match configuration.')
    for info in active.values():
        for mount in info.get('Mounts', []):
            source = Path(mount['Source']).resolve()
            if root == source or root in source.parents or source in root.parents:
                raise RuntimeError('Backups must not overlap mounted deployment storage.')
    env = dict(entry.split('=', 1) for entry in active['backend']['Config']['Env'])
    db_env = dict(entry.split('=', 1) for entry in active['db']['Config']['Env'])
    if env.get('DATABASE_URL') or env.get('POSTGRES_HOST', 'db') != 'db' or env.get('POSTGRES_DB') != db_env.get('POSTGRES_DB'):
        raise RuntimeError('External databases are not supported by this paired backup job.')


def archive_volume(stage, config, container, image, destination, filename, log):
    with (stage / filename).open('wb') as stream:
        execute(['docker', 'run', '--rm', '--network', 'none', '--volumes-from', container + ':ro',
                 '--entrypoint', 'tar', image, '-C', destination, '-cf', '-', '.'], stdout=stream, stderr=log)
    archive_manifest(stage / filename)


def verify_backup(path):
    checksums = read_json(path / 'checksums.json')
    for required in ('database.dump', 'files.tar', 'previous.json', 'inventory.json'):
        if required not in checksums:
            raise RuntimeError('Incomplete backup manifest.')
    for name, checksum in checksums.items():
        if Path(name).name != name or (path / name).is_symlink() or digest(path / name) != checksum:
            raise RuntimeError('Backup integrity check failed.')
    for name in checksums:
        if name.endswith('.tar') and name != 'images.tar':
            archive_manifest(path / name)
    return checksums


def encrypted_export(backup, settings, log):
    export = settings.get('export')
    if not export:
        return {'status': 'not_configured'}
    target = Path(export['directory']).resolve()
    # A missing remote mount must not silently turn into a local "offsite" copy.
    if (target / '.canary-backup-target').read_text().strip() != export['target_id']:
        raise RuntimeError('Backup export target marker is missing or incorrect.')
    secret = Path(export['passphrase_file']).resolve()
    mode = secret.stat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o077 or not secret.read_bytes().strip() or backup in secret.parents:
        raise RuntimeError('Export passphrase must be a nonempty private file outside the backup.')
    destination = target / (backup.name + '.tar.gpg')
    temporary = target / ('.' + destination.name + '.partial-' + uuid.uuid4().hex)
    try:
        # Stream encryption: no unencrypted aggregate archive, and no passphrase in argv.
        with subprocess.Popen(['gpg', '--batch', '--no-symkey-cache', '--pinentry-mode', 'loopback', '--passphrase-file', str(secret),
                               '--symmetric', '--cipher-algo', 'AES256', '--output', str(temporary)], stdin=subprocess.PIPE,
                              stdout=log, stderr=log) as process:
            try:
                with tarfile.open(fileobj=process.stdin, mode='w|') as archive:
                    for name in sorted(read_json(backup / 'checksums.json')) + ['checksums.json', 'backup.json']:
                        archive.add(backup / name, arcname=name, recursive=False)
                process.stdin.close()
                if process.wait(timeout=3600):
                    raise RuntimeError('Encrypted export failed.')
            except BaseException:
                process.kill(); process.wait(); raise
        os.chmod(temporary, 0o600)
        checksum = digest(temporary)
        os.replace(temporary, destination)
        atomic_json(target / (destination.name + '.sha256.json'), {'sha256': checksum})
        return {'status': 'ok', 'sha256': checksum, 'filename': destination.name}
    finally:
        temporary.unlink(missing_ok=True)


def verified_backups(root):
    result = []
    for path in root.glob('backup-*'):
        if path.is_symlink() or not path.is_dir():
            continue
        try:
            record = read_json(path / 'backup.json')
            if record.get('status') == 'verified':
                result.append((record['created_at'], path))
        except (OSError, ValueError, KeyError):
            continue
    return [path for _, path in sorted(result, reverse=True)]


def prune_backups(root, keep):
    # Only our explicitly verified directories; never incomplete jobs or arbitrary directories.
    backups = verified_backups(root)
    for path in backups[max(1, keep):]:
        shutil.rmtree(path)


def backup_job(settings):
    root = private_directory(settings['backup_dir'])
    state = private_directory(settings['state_dir'])
    config = resolved(settings)
    status_path = state / 'backup-status.json'
    status = read_json(status_path) if status_path.exists() else {}
    # Competing invocations must not overwrite the active job's status.
    with deploy.operation_lock(config['name']):
        stage = root / ('.incomplete-' + uuid.uuid4().hex)
        stage.mkdir(mode=0o700)
        status.update(status='running', last_attempt=now())
        atomic_json(status_path, status)
        try:
            active = inspect_running(settings['deployment_config'], config['services'])
            validate_backup_destination(root, config, active)
            for name, info in active.items():
                config['services'][name]['image'] = info['Image']
            atomic_json(stage / 'previous.json', config)
            targets = [name for name in deploy.dependents(config['services'], ['backend', 'frontend', 'radicale']) if name in active]
            manifest = {'containers': {name: info['Id'] for name, info in active.items()}}
            with (stage / 'backup.log').open('w') as log:
                try:
                    execute(deploy.compose(stage / 'previous.json', 'stop', *targets), stdout=log, stderr=log, timeout=180)
                    deploy.backup(stage, manifest, stderr=log)
                    archive_manifest(stage / 'files.tar')
                    script = Path(__file__).resolve().parents[1] / 'backend/scripts/recovery_inventory.py'
                    with script.open('rb') as source:
                        result = subprocess.check_output(deploy.compose(stage / 'previous.json', 'run', '--rm', '--no-deps', '-T',
                            '--entrypoint', 'python', 'backend', '-'), stdin=source, stderr=log, timeout=300)
                    inventory = json.loads(result)
                    if inventory['missing_file_ids']:
                        raise RuntimeError('Database references missing documents.')
                    atomic_json(stage / 'inventory.json', inventory)
                    for mount in active['backend']['Mounts']:
                        if mount['Destination'] in ('/radicale-data', '/commercial'):
                            filename = 'calendars.tar' if mount['Destination'] == '/radicale-data' else 'commercial.tar'
                            archive_volume(stage, config, active['backend']['Id'], active['backend']['Image'], mount['Destination'], filename, log)
                    env = config['services']['backend'].get('environment', {})
                    if (env.get('COMMERCIAL_MODULE_DIR') or env.get('COMMERCIAL_PACKAGE_DIR')) and not (stage / 'commercial.tar').exists():
                        raise RuntimeError('Optional package is configured but not captured at /commercial.')
                finally:
                    # Restart exactly the writers that were running, even after a partial stop/failure.
                    execute(deploy.compose(stage / 'previous.json', 'start', '--wait', '--wait-timeout', '240', *targets), stdout=log, stderr=log, timeout=300)
                # Image export does not need application downtime.
                if settings.get('archive_images', False):
                    with (stage / 'images.tar').open('wb') as stream:
                        execute(['docker', 'image', 'save', active['backend']['Image'], active['frontend']['Image']], stdout=stream, stderr=log, timeout=3600)
                checksums = {p.name: digest(p) for p in stage.iterdir() if p.name in (
                    'database.dump', 'files.tar', 'previous.json', 'inventory.json', 'calendars.tar', 'commercial.tar', 'images.tar')}
                atomic_json(stage / 'checksums.json', checksums)
                record = {'status': 'verified', 'created_at': now(), 'project': config['name'],
                          'schema_fingerprint': manifest['schema_before'], 'files_included': True}
                atomic_json(stage / 'backup.json', record)
                verify_backup(stage)
            final = root / ('backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8])
            stage.rename(final)
            status.update(last_verified_backup=str(final), last_verified_at=now())
            with (final / 'export.log').open('w') as log:
                status['export'] = encrypted_export(final, settings, log)
            status.update(status='ok', last_success=now(), error=None, finished_at=now())
            atomic_json(status_path, status)
            prune_backups(root, int(settings.get('keep_backups', 14)))
            return status
        except Exception as exc:
            status.update(status='failed', error=type(exc).__name__, finished_at=now())
            atomic_json(status_path, status)
            raise


def age_check(path, maximum_hours, success_field='last_success'):
    try:
        status = read_json(path)
        stamp = datetime.fromisoformat(status[success_field])
        age = (datetime.now(timezone.utc) - stamp).total_seconds() / 3600
        if stamp.tzinfo is None or age < 0:
            raise ValueError('Invalid timestamp')
        return {'status': 'ok' if age <= maximum_hours and status.get('status') == 'ok' else 'failed',
                'age_hours': round(age, 2), 'last_job_status': status.get('status')}
    except (OSError, ValueError, KeyError, TypeError):
        return {'status': 'failed', 'code': 'no_verified_success'}


def monitor_job(settings):
    state = private_directory(settings['state_dir'])
    checks = {}
    try:
        checks.update(read_json_output(deploy.compose(settings['deployment_config'], 'exec', '-T', 'backend',
                                                     'python', '-m', 'app.operational_health'))['checks'])
    except Exception:
        checks['application'] = {'status': 'failed', 'code': 'local_probe_unavailable'}
    try:
        with urllib.request.urlopen(settings['public_url'].rstrip('/') + '/api/health', timeout=5) as response:
            data = json.loads(response.read(4096))
        checks['public_access'] = {'status': 'ok' if data.get('status') == 'ok' else 'failed'}
    except Exception:
        # Does not attribute network/VPN/ingress failures to an application defect.
        checks['public_access'] = {'status': 'failed', 'code': 'public_access_unreachable'}
    checks['backup'] = age_check(state / 'backup-status.json', float(settings.get('max_backup_age_hours', 26)))
    checks['recovery'] = age_check(state / 'recovery-status.json', float(settings.get('max_recovery_age_days', 35)) * 24)
    report = {'checked_at': now(), 'status': 'ok' if all(c['status'] in ('ok', 'not_configured') for c in checks.values()) else 'failed', 'checks': checks}
    atomic_json(state / 'health-status.json', report)
    return report


def recovery_input(backup, settings, state):
    """When export is enabled, exercise the encrypted copy, not just local plaintext."""
    export = settings.get('export')
    if not export:
        return backup
    target = Path(export['directory']).resolve()
    if (target / '.canary-backup-target').read_text().strip() != export['target_id']:
        raise RuntimeError('Export target unavailable.')
    encrypted = target / (backup.name + '.tar.gpg')
    if digest(encrypted) != read_json(target / (encrypted.name + '.sha256.json'))['sha256']:
        raise RuntimeError('Encrypted backup checksum mismatch.')
    restored = state / ('recovery-input-' + uuid.uuid4().hex)
    restored.mkdir(mode=0o700)
    try:
        bundle = restored / '.bundle.tar'
        with bundle.open('wb') as stream, (restored / '.decrypt.log').open('w') as log:
            execute(['gpg', '--batch', '--no-symkey-cache', '--pinentry-mode', 'loopback', '--passphrase-file', export['passphrase_file'],
                     '--decrypt', str(encrypted)], stdout=stream, stderr=log, timeout=3600)
        archive_manifest(bundle)
        with tarfile.open(bundle) as archive:
            for member in archive:
                if Path(member.name).name != member.name or member.name not in (
                    'database.dump', 'files.tar', 'previous.json', 'inventory.json', 'checksums.json',
                    'backup.json', 'calendars.tar', 'commercial.tar', 'images.tar'):
                    raise RuntimeError('Unexpected encrypted bundle member.')
            archive.extractall(restored, filter='data')
        bundle.unlink()
        verify_backup(restored)
        return restored
    except BaseException:
        shutil.rmtree(restored)
        raise


def recovery_job(settings):
    state = private_directory(settings['state_dir'])
    with deploy.operation_lock(resolved(settings)['name']):
        status_path = state / 'recovery-status.json'
        status = read_json(status_path) if status_path.exists() else {}
        status.update(status='running', last_attempt=now()); atomic_json(status_path, status)
        source = None
        backup = None
        destination = None
        try:
            backups = verified_backups(Path(settings['backup_dir']))
            if not backups:
                raise RuntimeError('No verified backup available.')
            backup = backups[0]
            verify_backup(backup)
            source = recovery_input(backup, settings, state)
            previous = read_json(source / 'previous.json')
            destination = state / ('recovery-' + uuid.uuid4().hex)
            command = [sys.executable, str(Path(__file__).with_name('recovery_drill.py')), '--release', str(source),
                       '--state', str(destination), '--backend-image', previous['services']['backend']['image'],
                       '--frontend-image', previous['services']['frontend']['image'], '--verify', '--cleanup']
            with (state / 'recovery-job.log').open('w') as log:
                execute(command, stdout=log, stderr=log, timeout=1800)
            report = read_json(destination / 'recovery.json')
            if report['phase'] != 'verified':
                raise RuntimeError('Recovery verification incomplete.')
            status.update(status='ok', last_success=now(), backup=str(backup), report=str(destination / 'recovery.json'), error=None)
        except Exception as exc:
            status.update(status='failed', error=type(exc).__name__)
            raise
        finally:
            try:
                if destination is not None and (destination / 'compose.json').exists():
                    # Also runs when the child times out before its own finally block.
                    cleanup_recovery(destination)
                if source is not None and source != backup:
                    shutil.rmtree(source)
            except Exception as exc:
                status.update(status='failed', error=type(exc).__name__, cleanup='failed')
                raise
            finally:
                status['finished_at'] = now(); atomic_json(status_path, status)
        return status


def cleanup_recovery(destination):
    config = read_json(destination / 'compose.json')
    project = config['name']
    assert_isolated(config, project)
    execute(['docker', 'compose', '-p', project, '-f', str(destination / 'compose.json'),
             'down', '--volumes', '--remove-orphans'], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=180)


def interrupted(signum, frame):
    # Catchable so paired-backup restart and isolated-recovery cleanup run on SIGTERM.
    raise InterruptedError('Operations job interrupted.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('command', choices=['backup', 'monitor', 'recovery-check'])
    args = parser.parse_args()
    os.umask(0o077)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        settings = load_settings(args.config)
        job = {'backup': backup_job, 'monitor': monitor_job, 'recovery-check': recovery_job}[args.command]
        result = job(settings)
        # Public summary contains no paths, configuration, client data or exception text.
        print(json.dumps({'job': args.command, 'status': result['status'], 'time': now()}))
        return 0 if result['status'] == 'ok' else 1
    except Exception as exc:
        print(json.dumps({'job': args.command, 'status': 'failed', 'error_type': type(exc).__name__, 'time': now()}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
