"""Email identity hints produce reviewable locations, never an automatic filing decision."""
import re
from email.parser import BytesHeaderParser
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select
from app.deps import require_case_access
from app.models import File, Case
from app import file_storage
from app.file_eml_service import _row_is_eml_like


def normalize_message_id(value: str | None) -> str | None:
    value = (value or '').strip()
    if value.startswith('<') and value.endswith('>'):
        value = value[1:-1]
    if len(value) > 998 or not re.fullmatch(r'[^<>\s@]+@[^<>\s@]+', value):
        return None
    return value


def message_id_from_email(path: Path) -> str | None:
    try:
        with path.open('rb') as stream:
            raw = stream.read(131072)
        while raw.startswith(b'From ') and b'\n' in raw:
            raw = raw.split(b'\n', 1)[1]
        # Reject truncated/ambiguous headers instead of inventing an identity.
        if b'\r\n\r\n' not in raw and b'\n\n' not in raw:
            return None
        headers = BytesHeaderParser().parsebytes(raw)
        values = headers.get_all('Message-ID', [])
        if len(values) != 1:
            return None
        identity = normalize_message_id(str(values[0]))
        return '<' + identity + '>' if identity else None
    except (OSError, ValueError):
        return None


def filing_matches(payload, user, db):
    from app.schemas.files import MailFilingMatch
    identity = normalize_message_id(payload.internet_message_id)
    if not identity:
        return {'matches': [], 'lookup_status': 'no_exact_identifier', 'requires_confirmation': True}
    # Provider item IDs and IMAP tuples were client assertions without verified
    # account/UIDVALIDITY scope. Conversation IDs describe a thread, not a message.
    # None can independently establish an exact-message filing location.
    stmt = (select(File, Case).join(Case, File.case_id == Case.id)
            .where(File.source_internet_message_id.in_([identity, '<'+identity+'>']))
            .where(File.parent_file_id.is_(None), File.oo_compose_pending.is_(False))
            .order_by(File.created_at.desc(), File.id.desc())
            .execution_options(yield_per=100))
    matches = []
    accessible_index = 0
    for file, case in db.execute(stmt):
        try:
            require_case_access(case.id, user, db)
        except HTTPException as exc:
            if exc.status_code not in (403, 404):
                raise
            continue
        if not _row_is_eml_like(file):
            continue
        try:
            path = file_storage.assert_under_files_root(file_storage.FILES_ROOT / file.storage_path)
            actual = normalize_message_id(message_id_from_email(path))
        except (OSError, RuntimeError, ValueError):
            continue
        # Recheck historical rows too: old form-supplied IDs are not trusted.
        if actual != identity:
            continue
        if accessible_index < payload.offset:
            accessible_index += 1
            continue
        if len(matches) == 50:
            return {'matches': matches, 'lookup_status': 'possible_matches',
                    'requires_confirmation': True, 'next_offset': payload.offset + 50}
        matches.append(MailFilingMatch(id=case.id, case_number=case.case_number,
            client_name=case.client_name, matter_description=case.title,
            file_id=file.id, file_name=file.original_filename, folder_path=file.folder_path or ''))
    return {'matches': matches, 'lookup_status': 'possible_matches' if matches else 'no_match',
            'requires_confirmation': True}
