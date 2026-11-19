import os
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1]))
import operations as ops
import deploy


def fixture_backup(root, name='backup-20260101'):
    root.mkdir(exist_ok=True)
    path = root / name; path.mkdir()
    (path / 'database.dump').write_bytes(b'dump')
    for filename in ['previous.json', 'inventory.json']:
        (path / filename).write_text('{}')
    with tarfile.open(path / 'files.tar', 'w') as archive:
        info=tarfile.TarInfo('document.txt'); info.size=3; archive.addfile(info, io.BytesIO(b'abc'))
    ops.atomic_json(path / 'checksums.json', {p.name:ops.digest(p) for p in path.iterdir()})
    ops.atomic_json(path / 'backup.json', {'status':'verified','created_at':name})
    return path


class OperationsTests(unittest.TestCase):
    def test_manifest_checks_configuration_and_files_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            backup=fixture_backup(Path(folder))
            ops.verify_backup(backup)
            (backup/'previous.json').write_text('changed encryption key')
            with self.assertRaisesRegex(RuntimeError,'integrity'): ops.verify_backup(backup)

    def test_manifest_cannot_read_outside_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            backup=fixture_backup(Path(folder))
            checks=ops.read_json(backup/'checksums.json');checks['../secret']='hash'
            ops.atomic_json(backup/'checksums.json',checks)
            with self.assertRaises(RuntimeError): ops.verify_backup(backup)

    def test_retention_keeps_newest_and_never_touches_incomplete_or_unowned_directories(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            older=fixture_backup(root,'backup-1'); newest=fixture_backup(root,'backup-2')
            (root/'.incomplete-a').mkdir();(root/'backup-foreign').mkdir()
            ops.prune_backups(root,1)
            self.assertFalse(older.exists());self.assertTrue(newest.exists())
            self.assertTrue((root/'.incomplete-a').exists());self.assertTrue((root/'backup-foreign').exists())

    def test_backup_and_deployment_share_exclusive_lock(self):
        with deploy.operation_lock('unit-test-operations'):
            with self.assertRaises(BlockingIOError):
                with deploy.operation_lock('unit-test-operations'): pass

    def test_missing_stale_failed_and_future_status_are_not_healthy(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'status.json'
            self.assertEqual(ops.age_check(path,26)['status'],'failed')
            for hours,status,expected in [(1,'ok','ok'),(27,'ok','failed'),(1,'failed','failed'),(-1,'ok','failed')]:
                ops.atomic_json(path,{'last_success':(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat(),'status':status})
                self.assertEqual(ops.age_check(path,26)['status'],expected)

    def test_backup_failure_restarts_writers_and_does_not_rotate_or_mark_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); config={'name':'test','services':{'backend':{},'frontend':{},'db':{}}}
            active={key:{'Id':key,'Image':'image','Mounts':[],'Config':{'Env':[]}} for key in config['services']}
            settings={'backup_dir':str(root/'backups'),'state_dir':str(root/'state'),'deployment_config':'config'}
            with patch.object(ops,'resolved',return_value=config), patch.object(ops,'inspect_running',return_value=active), patch.object(ops,'validate_backup_destination'), patch.object(ops,'execute') as execute, patch.object(deploy,'backup',side_effect=OSError('sensitive disk failure')), patch.object(ops,'prune_backups') as prune:
                with self.assertRaises(OSError): ops.backup_job(settings)
                self.assertIn('stop',execute.call_args_list[0].args[0])
                self.assertIn('start',execute.call_args_list[-1].args[0])
                prune.assert_not_called()
                status=ops.read_json(root/'state/backup-status.json')
                self.assertEqual(status['status'],'failed');self.assertNotIn('last_success',status)
                self.assertNotIn('sensitive',json.dumps(status))

    def test_partial_stop_failure_still_attempts_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); config={'name':'test','services':{'backend':{},'frontend':{},'db':{}}}
            active={key:{'Id':key,'Image':'image','Mounts':[],'Config':{'Env':[]}} for key in config['services']}
            settings={'backup_dir':str(root/'backups'),'state_dir':str(root/'state'),'deployment_config':'config'}
            with patch.object(ops,'resolved',return_value=config), patch.object(ops,'inspect_running',return_value=active), patch.object(ops,'validate_backup_destination'), patch.object(ops,'execute',side_effect=[OSError('stop'),None]) as execute:
                with self.assertRaises(OSError): ops.backup_job(settings)
                self.assertIn('start',execute.call_args_list[-1].args[0])

    def test_missing_export_mount_does_not_encrypt_or_rotate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);backup=fixture_backup(root)
            settings={'export':{'directory':str(root/'missing'),'target_id':'expected'}}
            with patch.object(ops.subprocess,'Popen') as process:
                with self.assertRaises(OSError): ops.encrypted_export(backup,settings,io.StringIO())
                process.assert_not_called()

    def test_monitor_reports_local_and_public_failure_independently(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder);state.chmod(0o700)
            for name in ['backup','recovery']:
                ops.atomic_json(state/(name+'-status.json'),{'last_success':ops.now(),'status':'ok'})
            settings={'state_dir':folder,'deployment_config':'config','public_url':'https://example.invalid'}
            with patch.object(ops,'read_json_output',return_value={'checks':{'database':{'status':'ok'},'storage':{'status':'ok'},'onlyoffice':{'status':'ok'}}}), patch.object(ops.urllib.request,'urlopen',side_effect=TimeoutError('VPN detail')):
                result=ops.monitor_job(settings)
            self.assertEqual(result['status'],'failed')
            self.assertEqual(result['checks']['database']['status'],'ok')
            self.assertEqual(result['checks']['public_access']['code'],'public_access_unreachable')
            self.assertNotIn('VPN detail',json.dumps(result))

    @unittest.skipUnless(shutil.which('gpg'), 'GPG is required for encrypted exports')
    def test_encrypted_roundtrip_and_corruption_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            backup = fixture_backup(root)
            target = root / 'export'; target.mkdir()
            (target / '.canary-backup-target').write_text('fixture')
            secret = root / 'secret'; secret.write_text('unit-test-export-passphrase'); secret.chmod(0o600)
            home = root / 'gnupg'; home.mkdir(mode=0o700)
            settings = {'export': {'directory': str(target), 'target_id': 'fixture', 'passphrase_file': str(secret)}}
            with patch.dict(os.environ, {'GNUPGHOME': str(home)}), (root / 'private.log').open('w') as log:
                result = ops.encrypted_export(backup, settings, log)
                self.assertEqual(result['status'], 'ok')
                restored = ops.recovery_input(backup, settings, root)
                self.assertEqual(ops.verify_backup(restored), ops.verify_backup(backup))
                secret.write_text('wrong-passphrase')
                with self.assertRaises(subprocess.CalledProcessError):
                    ops.recovery_input(backup, settings, root)
                secret.write_text('unit-test-export-passphrase')
                encrypted = target / result['filename']
                with encrypted.open('ab') as stream: stream.write(b'corruption')
                with self.assertRaisesRegex(RuntimeError, 'checksum'):
                    ops.recovery_input(backup, settings, root)

    def test_cleanup_refuses_nonisolated_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ops.atomic_json(root/'compose.json', {'name':'production','networks':{'default':{'internal':False}}})
            with patch.object(ops,'execute') as execute:
                with self.assertRaises(RuntimeError): ops.cleanup_recovery(root)
                execute.assert_not_called()

    def test_recovery_timeout_cleans_isolated_project_and_records_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); backups = root/'backups'; backup = fixture_backup(backups)
            ops.atomic_json(backup/'previous.json', {'services':{'backend':{'image':'backend'},'frontend':{'image':'frontend'}}})
            settings = {'state_dir':str(root/'state'),'backup_dir':str(backups)}
            def timeout(command, **kwargs):
                destination = Path(command[command.index('--state')+1]); destination.mkdir()
                (destination/'compose.json').write_text('{}')
                raise subprocess.TimeoutExpired(command, 1800)
            with patch.object(ops,'resolved',return_value={'name':'unit-timeout'}), patch.object(ops,'verify_backup'), patch.object(ops,'execute',side_effect=timeout), patch.object(ops,'cleanup_recovery') as cleanup:
                with self.assertRaises(subprocess.TimeoutExpired): ops.recovery_job(settings)
                cleanup.assert_called_once()
            self.assertEqual(ops.read_json(root/'state/recovery-status.json')['status'],'failed')

    def test_failed_export_keeps_previous_success_and_does_not_rotate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture = fixture_backup(root/'fixture')
            state = root/'state'; state.mkdir(mode=0o700)
            previous_success = '2026-01-01T00:00:00+00:00'
            ops.atomic_json(state/'backup-status.json', {'status':'ok','last_success':previous_success})
            config = {'name':'unit-export-failure','services':{'backend':{},'frontend':{},'db':{}}}
            active = {key:{'Id':key,'Image':'image','Mounts':[],'Config':{'Env':[]}} for key in config['services']}
            settings = {'backup_dir':str(root/'backups'),'state_dir':str(state),'deployment_config':'config'}
            def snapshot(stage, manifest, **kwargs):
                for name in ['database.dump','files.tar']:
                    shutil.copyfile(fixture/name,stage/name)
                manifest['schema_before'] = 'schema'
            with patch.object(ops,'resolved',return_value=config), patch.object(ops,'inspect_running',return_value=active), patch.object(ops,'validate_backup_destination'), patch.object(ops,'execute'), patch.object(deploy,'backup',side_effect=snapshot), patch.object(ops.subprocess,'check_output',return_value=b'{"missing_file_ids":[]}'), patch.object(ops,'encrypted_export',side_effect=OSError('remote unavailable')), patch.object(ops,'prune_backups') as prune:
                with self.assertRaises(OSError): ops.backup_job(settings)
                prune.assert_not_called()
            status = ops.read_json(state/'backup-status.json')
            self.assertEqual(status['last_success'],previous_success)
            self.assertEqual(status['status'],'failed')
            ops.verify_backup(Path(status['last_verified_backup']))

    def test_backup_records_running_encryption_key_not_edited_compose_value(self):
        config = {'services':{'backend':{'image':'mutable-tag','environment':{'DATA_ENCRYPTION_KEY':'edited'}}}}
        active = {'backend':{'Image':'sha256:running','Config':{'Env':['DATA_ENCRYPTION_KEY=running==','POSTGRES_HOST=db']}}}
        ops.record_running_services(config,active)
        self.assertEqual(config['services']['backend']['image'],'sha256:running')
        self.assertEqual(config['services']['backend']['environment']['DATA_ENCRYPTION_KEY'],'running==')


if __name__=='__main__': unittest.main()
