"""Firm-wide portal / Canary Sign capability helpers."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.models import Case, FirmSettings
from app.portal_case import (
    case_portal_enabled,
    firm_canary_sign_enabled,
    firm_client_portal_enabled,
)


def test_firm_flags_default_true_when_no_row() -> None:
    db = MagicMock()
    db.get.return_value = None
    assert firm_client_portal_enabled(db) is True
    assert firm_canary_sign_enabled(db) is True


def test_firm_flags_read_settings() -> None:
    db = MagicMock()
    row = FirmSettings(id=1, client_portal_enabled=False, canary_sign_enabled=False)
    db.get.return_value = row
    assert firm_client_portal_enabled(db) is False
    assert firm_canary_sign_enabled(db) is False


def test_case_portal_requires_firm_and_matter() -> None:
    db = MagicMock()
    case_id = uuid.uuid4()
    settings = FirmSettings(id=1, client_portal_enabled=True, canary_sign_enabled=True)
    case = Case(id=case_id, portal_enabled=True)

    def _get(model, key):
        if model is FirmSettings:
            return settings
        if model is Case:
            return case
        return None

    db.get.side_effect = _get
    assert case_portal_enabled(db, case_id) is True
    settings.client_portal_enabled = False
    assert case_portal_enabled(db, case_id) is False
    settings.client_portal_enabled = True
    case.portal_enabled = False
    assert case_portal_enabled(db, case_id) is False
