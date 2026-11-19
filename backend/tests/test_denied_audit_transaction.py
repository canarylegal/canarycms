"""Rejected requests roll back business writes but retain minimal denial evidence."""
import json
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app import db as database
from app.models import User, AuditEvent


def test_denial_audit_survives_without_committing_rejected_write(monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    from sqlalchemy import JSON
    column = User.__table__.c.ui_preferences
    original = column.type
    try:
        column.type = JSON()
        User.__table__.create(engine)
    finally:
        column.type = original
    AuditEvent.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        user = User(email='audit@example.com', display_name='Before', initials='A', password_hash='unused')
        session.add(user); session.commit(); user_id = user.id
    monkeypatch.setattr(database, 'SessionLocal', factory)
    request = database.get_db()
    session = next(request)
    session.info['audit_request'] = {'actor_user_id': user_id, 'meta': {'method': 'DELETE', 'route': '/cases/{case_id}/files/{file_id}'}}
    session.get(User, user_id).display_name = 'Must roll back'
    session.flush()
    with pytest.raises(HTTPException):
        request.throw(HTTPException(403, 'sensitive reason must not be logged'))
    with factory() as check:
        assert check.get(User, user_id).display_name == 'Before'
        audit = check.scalars(select(AuditEvent)).one()
        assert audit.actor_user_id == user_id
        assert audit.action == 'access.denied'
        assert json.loads(audit.meta_json) == {'method': 'DELETE', 'route': '/cases/{case_id}/files/{file_id}'}
