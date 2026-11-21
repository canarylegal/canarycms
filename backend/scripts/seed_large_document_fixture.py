"""Additional synthetic 12k-document matter, called only by the guarded scale seeder."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.models import Case, CaseLockMode, File, FileCategory
from app.file_storage import FILES_ROOT

DOCUMENTS = 12000
ROOT_DOCUMENTS = 10000
ATTACHMENTS = 2000

def seed_large_documents(db, staff):
    matter = db.scalar(select(Case).where(Case.case_number == '900002'))
    matter.lock_mode = CaseLockMode.none
    folder = FILES_ROOT / 'large-performance'
    folder.mkdir(parents=True, exist_ok=True)
    ids = [uuid.uuid4() for _ in range(DOCUMENTS)]
    for i in range(DOCUMENTS):
        body = (f'Synthetic large-matter document {i}\n' * (1 + i % 40)).encode()
        path = folder / f'{i}.txt'
        path.write_bytes(body)
        deep = '/'.join([f'Branch {i % 40:02}'] + [f'Level {n:02}' for n in range(1, 21)])
        db.add(File(id=ids[i], case_id=matter.id, owner_id=staff.id, category=FileCategory.case_document,
            storage_path=str(path.relative_to(FILES_ROOT)), original_filename=f'Large document {i:05}.txt',
            mime_type='text/plain', size_bytes=len(body), checksum=hashlib.sha256(body).hexdigest(),
            folder_path='' if i < ROOT_DOCUMENTS else deep,
            parent_file_id=ids[0] if 1 <= i <= ATTACHMENTS else None,
            is_pinned=i == 0, source_mail_from_name='Synthetic sender' if i == 0 else None,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i)))
    db.flush()
