"""Synthetic document and ledger data ONLY in the disposable core-test database."""
import http.cookiejar
import json
import os
from pathlib import Path
import sys
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db import engine, SessionLocal
from app.models import Case

if os.getenv('CANARY_TEST_FIXTURE') != '1' or not (engine.url.database or '').endswith('_core_test'):
    raise RuntimeError('This fixture is restricted to the disposable core-test database.')
with SessionLocal() as db:
    case_id = str(db.scalar(select(Case.id).where(Case.case_number == '900001')))
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def request(path, data, content_type='application/json'):
    if content_type == 'application/json': data = json.dumps(data).encode()
    with opener.open(urllib.request.Request('http://frontend/api' + path, data=data,
                                           headers={'Content-Type':content_type}), timeout=20) as response:
        return response.status
request('/auth/login', {'email':os.environ['E2E_APPROVER_EMAIL'], 'password':os.environ['E2E_APPROVER_PASSWORD']})
payload = (b'--canary-fixture\r\nContent-Disposition: form-data; name="upload"; filename="recovery.txt"\r\n'
           b'Content-Type: text/plain\r\n\r\nSynthetic recovery document.\r\n--canary-fixture--\r\n')
assert request(f'/cases/{case_id}/files',payload,'multipart/form-data; boundary=canary-fixture') == 201
assert request(f'/cases/{case_id}/ledger/post',{'description':'Synthetic recovery receipt','amount_pence':12345,'client_direction':'credit'}) == 204
print('Synthetic document and nonzero ledger balance created.')

# Backup must authenticate pre-existing primary and legacy secrets after JWT rotation.
from app.models import User
from app.email_crypt import _fernet_from_jwt_secret, encrypt_password
with SessionLocal() as db:
    user = db.scalar(select(User).where(User.email == os.environ['E2E_APPROVER_EMAIL']))
    user.caldav_password_enc = _fernet_from_jwt_secret(os.environ['JWT_SECRET']).encrypt(b'synthetic-legacy-caldav').decode()
    another = db.scalar(select(User).where(User.email == os.environ['E2E_STAFF_EMAIL']))
    another.caldav_password_enc = encrypt_password('synthetic-primary-caldav')
    db.commit()
