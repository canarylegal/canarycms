"""Read-only restore inventory; run inside the isolated backend before enabling access."""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.db import engine

with engine.connect() as db:
    counts = {name: db.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one()
              for name in ['user', 'case', 'file', 'ledger_account', 'ledger_entry']}
    ledger_rows = [dict(row) for row in db.execute(text('SELECT * FROM ledger_entry ORDER BY id')).mappings()]
    ledger_fingerprint = hashlib.sha256(json.dumps(ledger_rows, default=str, sort_keys=True).encode()).hexdigest()
    balances = [dict(row) for row in db.execute(text("""
        SELECT a.case_id::text AS case_id, a.account_type::text AS account_type,
               COALESCE(SUM(CASE WHEN e.is_approved THEN CASE WHEN e.direction::text = 'credit' THEN e.amount_pence ELSE -e.amount_pence END ELSE 0 END), 0) AS balance_pence
        FROM ledger_account a LEFT JOIN ledger_entry e ON e.account_id = a.id
        GROUP BY a.case_id, a.account_type ORDER BY a.case_id, a.account_type
    """)).mappings()]
    files = [dict(row) for row in db.execute(text('SELECT id::text, storage_path, checksum FROM file ORDER BY id')).mappings()]
    missing = []
    for file in files:
        p = Path(file['storage_path'])
        if not p.is_absolute(): p = Path('/data/files') / p
        if not p.is_file(): missing.append(file['id'])
    revision = db.execute(text('SELECT version_num FROM alembic_version ORDER BY version_num')).scalars().all()
print(json.dumps(dict(counts=counts, ledger_fingerprint=ledger_fingerprint, balances=balances, missing_file_ids=missing, alembic_revision=revision), default=str, sort_keys=True))
