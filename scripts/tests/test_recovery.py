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


class CompleteBundleTests(unittest.TestCase):
    def test_recovery_preserves_decrypt_key_but_rotates_session_key(self):
        c = recovery.build_config('canaryrestore-keys', {'backend':'b','frontend':'f'}, 'data', None, legacy_jwt_secret='old')
        env=c['services']['backend']['environment']
        self.assertEqual(env['DATA_LEGACY_JWT_SECRET'], 'old')
        self.assertNotEqual(env['JWT_SECRET'], 'old')
        self.assertEqual(env['CANARY_COMMERCIAL_SERVICE_ENABLED'], '0')

    def fixture(self, root):
        import json
        roles={r:'sha256:'+str(i)*64 for i,r in enumerate(['backend','frontend','db','onlyoffice'],1)}
        previous={'services':{r:{'image':v} for r,v in roles.items()}}
        previous['services']['backend'].update(volumes=[{'target':'/commercial'},{'target':'/radicale-data'}],environment={})
        (root/'previous.json').write_text(json.dumps(previous))
        (root/'inventory.json').write_text(json.dumps({'integrity':{'ok':True}}))
        (root/'recovery-bundle.json').write_text(json.dumps({'version':1,'images':roles}))
        for name in ['files.tar','commercial.tar','calendars.tar']:
            with tarfile.open(root/name,'w'): pass
        return {n:'hash' for n in ['database.dump','files.tar','previous.json','inventory.json','images.tar','recovery-bundle.json','commercial.tar','calendars.tar']}, roles

    def test_complete_bundle_requires_optional_mounts_and_infrastructure(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); expected,roles=self.fixture(root)
            self.assertEqual(recovery.validate_bundle(root,expected),roles)
            for name in ['commercial.tar','calendars.tar','images.tar','inventory.json']:
                with self.subTest(name=name),self.assertRaises(RuntimeError):
                    recovery.validate_bundle(root,{k:v for k,v in expected.items() if k!=name})
            roles.pop('db');(root/'recovery-bundle.json').write_text(json.dumps({'version':1,'images':roles}))
            with self.assertRaises(RuntimeError):recovery.validate_bundle(root,expected)

    def test_images_import_before_inspect_without_registry_pull(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); expected,roles=self.fixture(root)
            with patch.object(recovery.subprocess,'run') as run, patch.object(recovery,'archive_image_configs',return_value=roles), patch.object(recovery.subprocess,'check_output',side_effect=lambda cmd,**kw:cmd[3]):
                self.assertEqual(recovery.load_bundle_images(root,expected,required=True),roles)
                self.assertEqual(run.call_args.args[0],['docker','image','load','-i',str(root/'images.tar')])

    def test_retired_scripts_cannot_execute_docker(self):
        import subprocess
        for name in ['backup-canary.sh','restore-canary.sh']:
            p=subprocess.run(['bash',str(Path(__file__).parents[1]/name),'anything'],capture_output=True,text=True)
            self.assertEqual(p.returncode,2)
            self.assertIn('No changes were made',p.stderr)

    def test_oci_index_resolves_to_classic_config_id(self):
        import json, hashlib
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'images.tar'
            config=json.dumps({'architecture':'amd64','os':'linux'}).encode()
            config_hash=hashlib.sha256(config).hexdigest()
            manifest=json.dumps({'config':{'digest':'sha256:'+config_hash}}).encode()
            manifest_hash=hashlib.sha256(manifest).hexdigest()
            index=json.dumps({'manifests':[{'digest':'sha256:'+manifest_hash}]}).encode()
            index_hash=hashlib.sha256(index).hexdigest()
            values={'blobs/sha256/'+config_hash:config,'blobs/sha256/'+manifest_hash:manifest,
                    'blobs/sha256/'+index_hash:index,'manifest.json':json.dumps([{'Config':'blobs/sha256/'+config_hash}]).encode()}
            with tarfile.open(path,'w') as archive:
                for name,data in values.items():
                    info=tarfile.TarInfo(name);info.size=len(data);archive.addfile(info,io.BytesIO(data))
            roles={'backend':'sha256:'+index_hash,'db':'sha256:'+config_hash}
            self.assertEqual(recovery.archive_image_configs(path,roles),{r:'sha256:'+config_hash for r in roles})

    def test_classic_import_falls_back_only_to_verified_config(self):
        from unittest.mock import patch
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);expected,roles=self.fixture(root)
            portable={r:'sha256:'+'a'*64 for r in roles}
            def inspect(cmd,**kw):
                if cmd[3] in roles.values():raise subprocess.CalledProcessError(1,cmd)
                return cmd[3]
            with patch.object(recovery.subprocess,'run'),patch.object(recovery,'archive_image_configs',return_value=portable),patch.object(recovery.subprocess,'check_output',side_effect=inspect):
                self.assertEqual(recovery.load_bundle_images(root,expected,True),portable)

    def test_legacy_only_installation_retains_original_data_key(self):
        import base64,hashlib
        expected=base64.urlsafe_b64encode(hashlib.sha256(b'original').digest()).decode()
        self.assertEqual(recovery.recovery_keys({'JWT_SECRET':'original'}),(expected,'original'))
        self.assertEqual(recovery.recovery_keys({'DATA_ENCRYPTION_KEY':'data','JWT_SECRET':'rotated','DATA_LEGACY_JWT_SECRET':'original'}),('data','original'))
        with self.assertRaises(RuntimeError): recovery.recovery_keys({})


if __name__ == '__main__':
    unittest.main()
