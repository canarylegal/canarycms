"""Create a temporary login ONLY in the isolated recovery database, never in a deployment."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db import SessionLocal, engine
from app.models import Case, File, User, UserRole
from app.security import hash_password

if engine.url.database != 'canary_recovery' or os.getenv('CANARY_BACKGROUND_JOBS_ENABLED') != '0':
    raise RuntimeError('This helper is only for the isolated canary_recovery database.')
with SessionLocal() as db:
    row = db.execute(select(File, Case).join(Case, Case.id == File.case_id).where(
        Case.title == 'Deployment verification', File.original_filename.like('%.docx')
    )).first()
    if row is None:
        raise RuntimeError('No restored verification matter/document. Choose a disposable document in the restored database before adapting this helper.')
    file, case = row
    password = secrets.token_urlsafe(24)
    suffix = secrets.token_hex(4)
    user = User(email=f'recovery-{suffix}@example.com', display_name='Recovery verification', initials='R'+suffix,
                role=UserRole.admin, is_active=True, password_hash=hash_password(password))
    db.add(user); db.commit()
    path = Path(file.storage_path)
    if not path.is_absolute(): path = Path('/data/files') / path
    with path.open('rb') as stream: original_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    print(json.dumps(dict(email=user.email, password=password, user_id=str(user.id), case_id=str(case.id),
                         case_number=case.case_number, title=case.title, file_id=str(file.id), filename=file.original_filename, original_hash=original_hash)))
