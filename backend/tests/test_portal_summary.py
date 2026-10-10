"""Portal summary desk options and empty feed."""

from __future__ import annotations

from app.models import UserRole
from app.portal_summary_service import list_portal_summary, portal_summary_options
from tests.ledger_test_helpers import add_user, ledger_test_session


def test_portal_summary_options_shape() -> None:
    db = ledger_test_session()
    opts = portal_summary_options(db)
    assert hasattr(opts, "enabled")
    assert hasattr(opts, "client_portal_enabled")
    assert hasattr(opts, "canary_sign_enabled")
    assert hasattr(opts, "docusign_enabled")


def test_portal_summary_empty_for_new_user() -> None:
    db = ledger_test_session()
    user = add_user(db, role=UserRole.admin)
    rows = list_portal_summary(db, user=user, bucket="outstanding")
    assert rows == []
    rows_done = list_portal_summary(db, user=user, bucket="completed")
    assert rows_done == []
