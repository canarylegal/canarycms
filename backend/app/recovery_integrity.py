"""Read-only, provider-free backup validation. Reports counts, never secret values."""
import base64
import hashlib
from pathlib import Path
from sqlalchemy import inspect, text
from app.email_crypt import decrypt_password


def check_bytes(root, rows):
    root = Path(root).resolve()
    result = dict(checked=0, missing=0, invalid_path=0, mismatched=0, unknown_checksum=0)
    for row in rows:
        result['checked'] += 1
        path = (root / row['storage_path']).resolve()
        if not path.is_relative_to(root):
            result['invalid_path'] += 1
        elif not path.is_file():
            result['missing'] += 1
        elif not row['checksum']:
            result['unknown_checksum'] += 1
        else:
            with path.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != row['checksum']:
                result['mismatched'] += 1
    return result


def check_secret(value, *, totp=False):
    if totp and not value.startswith('gAAAA'):
        # Historical plaintext TOTP is base32, not arbitrary undecryptable ciphertext.
        try:
            if len(base64.b32decode(value, casefold=True)) >= 10:
                return True
        except (ValueError, TypeError):
            pass
    try:
        decrypt_password(value)
        return True
    except Exception:
        # Never include a ciphertext, plaintext, database ID or crypto exception text.
        return False


def audit(db, root):
    tables = set(inspect(db).get_table_names())
    result = {'files': check_bytes(root, db.execute(text('SELECT storage_path, checksum FROM file')).mappings())}
    if 'document_recovery' in tables:
        result['recovery'] = check_bytes(root, db.execute(text('SELECT storage_path, checksum FROM document_recovery WHERE storage_path IS NOT NULL')).mappings())
        result['historically_unavailable_recovery'] = db.execute(text('SELECT count(*) FROM document_recovery WHERE storage_path IS NULL')).scalar_one()
    result['invalid_attachment_links'] = db.execute(text('''SELECT count(*) FROM file f LEFT JOIN file p ON p.id=f.parent_file_id
        WHERE f.parent_file_id IS NOT NULL AND (p.id IS NULL OR p.id=f.id OR p.case_id IS DISTINCT FROM f.case_id)''')).scalar_one()
    secrets = dict(checked=0, failed=0)
    quote = db.dialect.identifier_preparer.quote
    for table in sorted(tables):
        for column in inspect(db).get_columns(table):
            name = column['name']
            if not (name.endswith('_enc') or (table == 'user' and name == 'totp_secret')):
                continue
            for value in db.execute(text(f'SELECT {quote(name)} FROM {quote(table)} WHERE {quote(name)} IS NOT NULL')).scalars():
                if not value:
                    continue
                secrets['checked'] += 1
                if not check_secret(value, totp=name == 'totp_secret'):
                    secrets['failed'] += 1
    result['secrets'] = secrets
    result['ok'] = not (secrets['failed'] or result['invalid_attachment_links'] or any(
        values.get(key, 0) for name, values in result.items() if name in ('files', 'recovery')
        for key in ('missing', 'invalid_path', 'mismatched')))
    return result
