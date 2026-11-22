"""Synthetic migration preservation check, only in the dedicated disposable runner."""
import os
import json
import sys
from pathlib import Path
from sqlalchemy import text
from app.db import engine

assert os.environ.get('COMMERCIAL_FOUNDATION_TEST')=='1'
assert os.environ.get('CANARY_BACKGROUND_JOBS_ENABLED')=='0'
state=Path('/tmp/commercial-migration-before.json')
with engine.begin() as db:
    if sys.argv[1]=='prepare':
        db.execute(text("INSERT INTO hmlr_integration_settings (id, enabled, sandbox, username, password_enc) VALUES (1,false,true,'synthetic-migration-user','synthetic-ciphertext') ON CONFLICT (id) DO UPDATE SET username=EXCLUDED.username, password_enc=EXCLUDED.password_enc"))
        rows=db.execute(text('SELECT row_to_json(s)::text FROM hmlr_integration_settings s')).scalars().all()
        state.write_text(json.dumps(rows))
    else:
        rows=db.execute(text('SELECT row_to_json(s)::text FROM hmlr_integration_settings s')).scalars().all()
        assert rows==json.loads(state.read_text())
        for table in ['commercial_connection','commercial_credential','commercial_operation','commercial_application']:
            assert db.execute(text('SELECT count(*) FROM '+table)).scalar()==0
        print('PASS: existing integration settings unchanged; new tables empty')
