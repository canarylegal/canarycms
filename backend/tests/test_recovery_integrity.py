import hashlib
from pathlib import Path
import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, text
from app.email_crypt import _fernet_from_jwt_secret, decrypt_password, encrypt_password
from app.recovery_integrity import audit, check_bytes, check_secret


def test_recovery_legacy_key_is_decryption_only(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setenv('DATA_ENCRYPTION_KEY', key.decode())
    monkeypatch.setenv('JWT_SECRET', 'new-session-signing-secret')
    monkeypatch.setenv('DATA_LEGACY_JWT_SECRET', 'original-session-secret')
    old = _fernet_from_jwt_secret('original-session-secret').encrypt(b'credential').decode()
    assert decrypt_password(old) == 'credential'
    assert Fernet(key).decrypt(encrypt_password('new').encode()) == b'new'
    monkeypatch.delenv('DATA_LEGACY_JWT_SECRET')
    with pytest.raises(InvalidToken): decrypt_password(old)


def test_known_corruption_missing_and_outside_paths_fail(tmp_path):
    (tmp_path/'good').write_bytes(b'good')
    rows = [dict(storage_path='good', checksum=hashlib.sha256(b'wrong').hexdigest()),
            dict(storage_path='missing', checksum='x'),dict(storage_path='../outside',checksum=None),
            dict(storage_path='good',checksum=None)]
    assert check_bytes(tmp_path, rows) == dict(checked=4, missing=1, invalid_path=1, mismatched=1, unknown_checksum=1)


def test_encrypted_totp_never_falls_back_to_plaintext():
    assert check_secret('JBSWY3DPEHPK3PXPJBSWY3DP', totp=True)
    assert not check_secret('gAAAA-invalid-ciphertext', totp=True)
    assert not check_secret('not-a-valid-secret', totp=True)


def test_inventory_checks_archived_versions_attachments_and_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_ENCRYPTION_KEY', Fernet.generate_key().decode())
    (tmp_path/'live').write_bytes(b'live')
    (tmp_path/'archive').write_bytes(b'damaged')
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        for sql in ['create table file (id integer, parent_file_id integer, case_id integer, storage_path text, checksum text)',
                    'create table document_recovery (storage_path text, checksum text)',
                    'create table credential (secret_enc text)', 'create table "user" (totp_secret text)']:
            db.execute(text(sql))
        db.execute(text("insert into file values(1,99,1,'live',NULL)"))
        db.execute(text("insert into document_recovery values('archive',:checksum)"),{'checksum':hashlib.sha256(b'original').hexdigest()})
        db.execute(text("insert into credential values('invalid')"))
        result = audit(db, tmp_path)
        assert not result['ok']
        assert result['files']['unknown_checksum'] == 1
        assert result['recovery']['mismatched'] == 1
        assert result['invalid_attachment_links'] == 1
        assert result['secrets'] == {'checked':1,'failed':1}
        db.execute(text('update credential set secret_enc=:value'), {'value':encrypt_password('synthetic')})
        db.execute(text('update file set parent_file_id=NULL'))
        (tmp_path/'archive').write_bytes(b'original')
        assert audit(db, tmp_path)['ok']


def test_preserved_decryption_key_does_not_validate_old_sessions(monkeypatch):
    from app import security
    monkeypatch.setattr(security, 'JWT_SECRET', 'original-session-key')
    old = security.create_access_token(user_id='synthetic-user', role='admin')
    monkeypatch.setenv('DATA_LEGACY_JWT_SECRET', 'original-session-key')
    monkeypatch.setattr(security, 'JWT_SECRET', 'rotated-session-key')
    with pytest.raises(ValueError): security.decode_access_token(old)
    new = security.create_access_token(user_id='synthetic-user', role='admin')
    assert security.decode_access_token(new).user_id == 'synthetic-user'
