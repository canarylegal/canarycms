"""Portal summary desk options and empty feed."""

from __future__ import annotations

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Base,
    CanarySignRecipient,
    CanarySignRequest,
    Case,
    Contact,
    File,
    FirmSettings,
    PortalFormSubmission,
    PortalFormTemplate,
    QuotePortalDelivery,
    User,
    UserRole,
)
from app.portal_summary_service import list_portal_summary, portal_summary_options
from tests.ledger_test_helpers import add_user


def _portal_summary_session() -> Session:
    """SQLite session with tables touched by list_portal_summary collectors."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    patched: list[tuple[object, object]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                patched.append((column, column.type))
                column.type = JSON()
    tables = (
        User.__table__,
        Case.__table__,
        Contact.__table__,
        File.__table__,
        FirmSettings.__table__,
        QuotePortalDelivery.__table__,
        PortalFormTemplate.__table__,
        PortalFormSubmission.__table__,
        CanarySignRequest.__table__,
        CanarySignRecipient.__table__,
    )
    try:
        for table in tables:
            table.create(engine, checkfirst=True)
    finally:
        for column, original in patched:
            column.type = original
    return sessionmaker(bind=engine)()


def test_portal_summary_options_shape() -> None:
    db = _portal_summary_session()
    opts = portal_summary_options(db)
    assert hasattr(opts, "enabled")
    assert hasattr(opts, "client_portal_enabled")
    assert hasattr(opts, "canary_sign_enabled")
    assert hasattr(opts, "docusign_enabled")


def test_portal_summary_empty_for_new_user() -> None:
    db = _portal_summary_session()
    # Explicit firm flags on (same default as missing row) so collectors run against empty tables.
    db.add(FirmSettings(id=1, client_portal_enabled=True, canary_sign_enabled=True))
    db.commit()
    user = add_user(db, role=UserRole.admin)
    rows = list_portal_summary(db, user=user, bucket="outstanding")
    assert rows == []
    rows_done = list_portal_summary(db, user=user, bucket="completed")
    assert rows_done == []
