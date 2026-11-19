"""Authenticated checks in a restored clone; never allowed against a deployment."""
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import pyotp
import urllib.request
import urllib.error
from sqlalchemy import select, text
from app.db import SessionLocal, engine
from app.models import Case, File, User, UserRole
from app.security import hash_password, generate_totp_secret
from app.totp_secrets import encrypt_totp_secret

if engine.url.database != 'canary_recovery' or os.getenv('CANARY_BACKGROUND_JOBS_ENABLED') != '0':
    raise RuntimeError('Verification is restricted to the isolated recovery database.')

password = secrets.token_urlsafe(32)
totp_secret = generate_totp_secret()
with SessionLocal() as db:
    user = User(email='recovery-' + secrets.token_hex(8) + '@example.com', display_name='Recovery check',
                initials='R' + secrets.token_hex(5), role=UserRole.admin, is_active=True,
                is_2fa_enabled=True, totp_secret=encrypt_totp_secret(totp_secret),
                password_changed_at=datetime.now(timezone.utc), password_hash=hash_password(password))
    db.add(user); db.commit(); user_id = user.id; email = user.email
    cases = db.scalars(select(Case.id)).all()
    files = db.execute(select(File.id, File.case_id, File.storage_path).where(File.case_id.is_not(None)).order_by(File.id).limit(3)).all()
    balances = [dict(row) for row in db.execute(text("""
        SELECT a.case_id::text AS case_id, a.account_type::text AS account_type,
        COALESCE(SUM(CASE WHEN e.is_approved THEN CASE WHEN e.direction::text='credit'
        THEN e.amount_pence ELSE -e.amount_pence END ELSE 0 END),0) AS balance_pence
        FROM ledger_account a LEFT JOIN ledger_entry e ON e.account_id=a.id
        GROUP BY a.case_id,a.account_type
    """)).mappings()]

opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def request(path, data=None):
    payload = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request('http://frontend/api' + path, data=payload,
                                 headers={'Content-Type': 'application/json'})
    try:
        return opener.open(req, timeout=15)
    except urllib.error.HTTPError as error:
        # Private verifier log: validation location/type, never inputs or credentials.
        try:
            details = json.load(error).get('detail', [])
            validation = [{'loc': item.get('loc'), 'type': item.get('type')} for item in details if isinstance(item, dict)]
        except (ValueError, AttributeError, TypeError):
            validation = []
        raise RuntimeError(json.dumps({'status': error.code, 'validation': validation})) from None

try:
    with request('/auth/login', {'email': email, 'password': password, 'totp_code': pyotp.TOTP(totp_secret).now()}) as response:
        assert response.status == 200
    with request('/auth/me') as response:
        assert json.load(response)['id'] == str(user_id)
    with request('/health') as response:
        assert response.status == 200
    if cases:
        with request('/cases/' + str(cases[0])) as response:
            assert json.load(response)['id'] == str(cases[0])
    for file_id, case_id, storage_path in files:
        path = Path(storage_path)
        if not path.is_absolute(): path = Path('/data/files') / path
        with path.open('rb') as stream:
            expected = hashlib.file_digest(stream, 'sha256').hexdigest()
        actual = hashlib.sha256()
        with request(f'/cases/{case_id}/files/{file_id}') as response:
            while chunk := response.read(1024 * 1024): actual.update(chunk)
        assert actual.hexdigest() == expected
    for case_id in {row['case_id'] for row in balances}:
        with request(f'/cases/{case_id}/ledger') as response: ledger = json.load(response)
        for row in balances:
            if row['case_id'] == case_id:
                assert ledger[row['account_type']]['balance_pence'] == row['balance_pence']
    with request('/auth/logout', {}) as response:
        assert response.status in (200, 204)
    print(json.dumps({'status': 'verified', 'login': True, 'matter_checked': bool(cases),
                      'documents_checked': len(files), 'ledger_accounts_checked': len(balances), 'logout': True}))
finally:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        user.is_active = False; user.auth_token_version += 1
        user.password_hash = hash_password(secrets.token_urlsafe(32)); db.commit()
