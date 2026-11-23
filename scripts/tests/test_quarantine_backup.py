import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1]))
import deploy

class QuarantineBackupTests(unittest.TestCase):
    def test_pending_bytes_have_a_separate_verified_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            release=Path(folder)
            (release/'previous.json').write_text(json.dumps({'services':{'backend':{'image':'synthetic-image','environment':{'CANARY_QUARANTINE_ROOT':'/data/quarantine'}}}}))
            seen=[]
            def fake_run(args,**kwargs):
                seen.append(args)
                if 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' in args:
                    kwargs['stdout'].write(b'synthetic-dump')
                elif 'tar' in args:
                    root=args[args.index('-C')+1]
                    data=b'quarantined' if root=='/data/quarantine' else b'clean'
                    with tarfile.open(fileobj=kwargs['stdout'],mode='w') as archive:
                        member=tarfile.TarInfo('synthetic');member.size=len(data)
                        archive.addfile(member,io.BytesIO(data))
            manifest={'containers':{'db':'synthetic-db','backend':'synthetic-backend'}}
            with patch.object(deploy,'schema_fingerprint',return_value='synthetic-schema'),patch.object(deploy,'inspect',return_value={'Mounts':[{'Destination':'/data/quarantine'}]}),patch.object(deploy.subprocess,'run',side_effect=fake_run):
                deploy.backup(release,manifest)
            sums=json.loads((release/'checksums.json').read_text())
            self.assertEqual(set(sums),{'database.dump','files.tar','quarantine.tar'})
            self.assertEqual(sums['quarantine.tar'],hashlib.sha256((release/'quarantine.tar').read_bytes()).hexdigest())
            self.assertTrue(any('/data/quarantine' in args and '--network' in args and 'none' in args for args in seen))

if __name__=='__main__':unittest.main()
