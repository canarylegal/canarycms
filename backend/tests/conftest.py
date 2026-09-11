"""Ensure required env vars exist before `app` (and SQLAlchemy engine) is imported."""

from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# Tests must not require a live Postgres if unset (e.g. CI); override with DATABASE_URL for integration runs.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
# decode_access_token and similar use JWT secret at import/runtime
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-pytest-only")
os.environ.setdefault(
    "DATA_ENCRYPTION_KEY",
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
)
# app.file_storage resolves FILES_ROOT at import — routers load before tests without Docker env.
_files_root = os.path.join(tempfile.gettempdir(), "canary-pytest-files-root")
os.makedirs(_files_root, exist_ok=True)
os.environ.setdefault("FILES_ROOT", _files_root)
# Importing app.main validates master recovery env at module load (same as production startup).
os.environ.setdefault("MASTER_ADMIN_LOGIN", "ci-master-pytest-admin")
os.environ.setdefault("MASTER_ADMIN_PASSWORD", "ci-master-pytest-password")
os.environ.setdefault("MASTER_ADMIN_REQUIRE_2FA", "false")
os.environ.setdefault("MASTER_ADMIN_TOTP_SECRET", "")


@pytest.fixture
def db():
    """Shared DB session for tests that need a migrated schema (Postgres in CI with DATABASE_URL).

    Default CI uses in-memory SQLite without migrations — those tests skip rather than error.
    """
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        session.execute(text('SELECT 1 FROM "case" LIMIT 1'))
    except SQLAlchemyError:
        session.close()
        pytest.skip("requires migrated Postgres (set DATABASE_URL)")
    try:
        yield session
        session.rollback()
    finally:
        session.close()
