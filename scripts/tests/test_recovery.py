import importlib.util
from pathlib import Path
import tempfile
import tarfile
import io
import unittest

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).parents[1] / 'recovery_drill.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class RecoverySafetyTests(unittest.TestCase):
    def test_isolated_configuration_does_not_inherit_integrations_or_live_mounts(self):
        project = 'canaryrestore-test'
        config = recovery.build_config(project, {'backend': 'sha256:b', 'frontend': 'sha256:f'}, 'key', None)
        recovery.assert_isolated(config, project)
        self.assertTrue(config['networks']['default']['internal'])
        self.assertNotIn('CANARY_MS_GRAPH_CLIENT_SECRET', config['services']['backend']['environment'])
        self.assertEqual(config['services']['backend']['environment']['CANARY_BACKGROUND_JOBS_ENABLED'], '0')
        self.assertEqual(config['services']['backend']['volumes'], [{'type': 'volume', 'source': 'files', 'target': '/data/files'}])
        for service in config['services'].values():
            self.assertNotIn('ports', service)
            self.assertNotIn('container_name', service)

    def test_commercial_module_path_stays_inside_private_package(self):
        config = recovery.build_config('canaryrestore-test', {'backend': 'b', 'frontend': 'f'}, 'key', Path('/private/copy'), '/commercial/module')
        self.assertEqual(config['services']['backend']['environment']['COMMERCIAL_MODULE_DIR'], '/commercial/module')
        with self.assertRaises(RuntimeError):
            recovery.build_config('canaryrestore-test', {'backend': 'b', 'frontend': 'f'}, 'key', Path('/private/copy'), '/commercial/../live')

    def test_live_project_or_volume_or_port_is_refused(self):
        for change in ['project', 'volume', 'port', 'network']:
            project = 'canaryrestore-test'
            config = recovery.build_config(project, {'backend': 'b', 'frontend': 'f'}, 'key', None)
            if change == 'project': project = 'canary'
            if change == 'volume': config['volumes']['database']['name'] = 'canary_db-data'
            if change == 'port': config['services']['frontend']['ports'] = ['80:80']
            if change == 'network': config['networks']['default']['internal'] = False
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                recovery.assert_isolated(config, project)

    def test_archive_rejects_traversal_absolute_paths_and_links(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('/absolute', tarfile.REGTYPE), ('link', tarfile.SYMTYPE), ('link', tarfile.LNKTYPE)]:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'files.tar'
                with tarfile.open(path, 'w') as archive:
                    info = tarfile.TarInfo(name); info.type = kind
                    info.linkname = '/outside'
                    archive.addfile(info)
                with self.subTest(name=name, kind=kind), self.assertRaises(RuntimeError):
                    recovery.archive_manifest(path)

    def test_manifest_hashes_contents_and_rejects_duplicate_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'files.tar'
            with tarfile.open(path, 'w') as archive:
                info = tarfile.TarInfo('./document'); info.size = 3
                archive.addfile(info, io.BytesIO(b'abc'))
            self.assertEqual(recovery.archive_manifest(path), {'document': 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'})
            with tarfile.open(path, 'a') as archive:
                info = tarfile.TarInfo('document'); info.size = 3
                archive.addfile(info, io.BytesIO(b'abc'))
            with self.assertRaisesRegex(RuntimeError, 'Duplicate'):
                recovery.archive_manifest(path)

if __name__ == '__main__':
    unittest.main()
