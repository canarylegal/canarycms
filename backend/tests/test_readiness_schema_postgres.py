"""Readiness against disposable databases, never deployment databases."""
import uuid
import pytest
import psycopg
from psycopg import sql
from app import db as database, operational_health as health


@pytest.fixture
def schema_database(monkeypatch):
    url = database.engine.url
    if url.get_backend_name() != 'postgresql':
        pytest.skip('Requires isolated PostgreSQL')
    name = 'audit_health_' + uuid.uuid4().hex[:12]
    admin = url.set(drivername='postgresql').render_as_string(hide_password=False)
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    monkeypatch.setattr(database, 'DATABASE_URL', url.set(database=name).render_as_string(hide_password=False))
    try:
        with psycopg.connect(url.set(drivername='postgresql', database=name).render_as_string(hide_password=False), autocommit=True) as connection:
            yield connection
    finally:
        with psycopg.connect(admin, autocommit=True) as connection:
            connection.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))


def test_migrated_core_is_ready():
    if database.engine.dialect.name != 'postgresql': pytest.skip('Requires migrated PostgreSQL')
    assert health.database_probe() == {'status': 'ok'}


def test_empty_database_is_not_ready(schema_database, tmp_path, monkeypatch):
    from app import file_storage
    monkeypatch.setattr(file_storage, 'FILES_ROOT', tmp_path)
    monkeypatch.setenv('CANARY_STORAGE_MIN_FREE_BYTES', '0')
    snapshot = health.health_snapshot(include_office=False)
    assert snapshot['ready'] is False
    assert snapshot['checks']['database'] == {'status': 'failed', 'code': 'database_unavailable'}


@pytest.mark.parametrize('revisions', [[], ['outdated'], ['unknown-future'], ['outdated', 'other-branch']])
def test_missing_or_mismatched_revision_is_not_ready(schema_database, revisions):
    schema_database.execute('CREATE TABLE alembic_version(version_num varchar(64))')
    for revision in revisions:
        schema_database.execute('INSERT INTO alembic_version VALUES (%s)', (revision,))
    assert health.database_probe() == {'status': 'failed', 'code': 'database_schema_mismatch'}


@pytest.mark.parametrize('missing', ['user', 'case', 'file', 'file-column'])
def test_stamped_partial_schema_is_not_ready(schema_database, missing):
    schema_database.execute('CREATE TABLE alembic_version(version_num varchar(64))')
    for head in health._expected_schema_heads():
        schema_database.execute('INSERT INTO alembic_version VALUES (%s)', (head,))
    statements = {
        'user': 'CREATE TABLE "user"(id uuid, email text)',
        'case': 'CREATE TABLE "case"(id uuid, fee_earner_user_id uuid)',
        'file': 'CREATE TABLE "file"(id uuid, case_id uuid, storage_path text, version int)',
    }
    for name, statement in statements.items():
        if name != missing:
            schema_database.execute(statement)
    if missing == 'file-column':
        schema_database.execute('ALTER TABLE "file" DROP COLUMN storage_path')
    assert health.probe('database', health.database_probe) == {'status': 'failed', 'code': 'database_unavailable'}
