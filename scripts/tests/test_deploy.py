"""Safety contracts; no Docker daemon or live database is used by these tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('deploy', Path(__file__).parents[1] / 'deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeploySafetyTests(unittest.TestCase):
    def test_network_companions_are_recreated_transitively(self):
        services = {'backend': {}, 'frontend': {}, 'tunnel': {'network_mode': 'service:frontend'},
                    'helper': {'network_mode': 'service:tunnel'}, 'db': {}}
        self.assertEqual(deploy.dependents(services, ['backend', 'frontend']), ['backend', 'frontend', 'helper', 'tunnel'])

    def test_mount_identity_includes_actual_named_volume_and_file_path(self):
        config = {'services': {'backend': {'volumes': [
            {'type': 'volume', 'source': 'files', 'target': '/data/files'},
            {'type': 'bind', 'source': '/srv/firm', 'target': '/firm'}]}},
            'volumes': {'files': {'name': 'existing_firm_files'}}}
        self.assertEqual(deploy.configured_data_identity(config, 'backend'),
                         [('/data/files', 'volume', 'existing_firm_files'), ('/firm', 'bind', '/srv/firm')])

    def test_dirty_source_refused(self):
        with patch.object(deploy, 'output', return_value=' M frontend/src/App.tsx'):
            with self.assertRaisesRegex(RuntimeError, 'Commit or stash'):
                deploy.ensure_source(Path('/repo'))

    def test_source_changed_after_prepare_refused(self):
        with patch.object(deploy, 'output', side_effect=['', 'new-commit']):
            with self.assertRaisesRegex(RuntimeError, 'Source commit changed'):
                deploy.ensure_source(Path('/repo'), 'old-commit')

    def test_schema_change_blocks_code_rollback_without_running_commands(self):
        with patch.object(deploy, 'output', return_value='db'), patch.object(deploy, 'schema_fingerprint', return_value='after'), patch.object(deploy, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Schema changed'):
                deploy.rollback(Path('/release'), {'schema_before': 'before'})
            run.assert_not_called()

    def test_rollback_keeps_database_and_volumes_and_verifies_old_commit(self):
        manifest = {'schema_before': 'same', 'targets': ['backend', 'frontend'], 'previous_commit': 'old'}
        with tempfile.TemporaryDirectory() as folder, patch.object(deploy, 'output', return_value='db'), patch.object(deploy, 'schema_fingerprint', return_value='same'), patch.object(deploy, 'run') as run, patch.object(deploy, 'verify') as verify:
            path = Path(folder)
            deploy.rollback(path, manifest)
            args = run.call_args.args[0]
            self.assertIn('--no-build', args)
            self.assertIn('--no-deps', args)
            self.assertNotIn('down', args)
            self.assertNotIn('--volumes', args)
            verify.assert_called_once_with(path / 'previous.json', manifest, 'old')
            self.assertEqual(manifest['phase'], 'rolled_back')

    def test_reapplying_release_cannot_overwrite_backups(self):
        with self.assertRaisesRegex(RuntimeError, 'already attempted'):
            deploy.apply(Path('/release'), {'phase': 'verified'})

    def test_backup_failure_restarts_old_services_without_applying_new_images(self):
        manifest = {'phase': 'prepared', 'source': '/repo', 'commit': 'sha',
                    'containers': {'backend': 'id'}, 'targets': ['backend', 'frontend']}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            deploy.save(path / 'compose.json', {'services': {'backend': {'image': 'new-backend'}, 'frontend': {'image': 'new-frontend'}}})
            with patch.object(deploy, 'ensure_source'), patch.object(deploy, 'output', side_effect=['id', 'image-backend', 'image-frontend', 'id']), patch.object(deploy, 'backup', side_effect=RuntimeError('disk full')), patch.object(deploy, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'disk full'):
                    deploy.apply(path, manifest)
                commands = [call.args[0] for call in run.call_args_list]
                self.assertEqual(commands[-1][-3:], ['start', 'backend', 'frontend'])
                self.assertFalse(any('up' in command for command in commands))


if __name__ == '__main__':
    unittest.main()
