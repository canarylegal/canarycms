"""Ledger Excel export helpers."""

from datetime import datetime, timezone
from uuid import uuid4

from app.ledger_export import _entry_pending, _running_balances
from app.schemas import LedgerEntryOut


def _entry(**kwargs) -> LedgerEntryOut:
    defaults = {
        "id": uuid4(),
        "pair_id": uuid4(),
        "account_type": "office",
        "direction": "debit",
        "amount_pence": 10000,
        "description": "Test",
        "reference": None,
        "contact_label": None,
        "case_contact_id": None,
        "contact_id": None,
        "posted_by_user_id": None,
        "posted_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "is_approved": True,
    }
    defaults.update(kwargs)
    return LedgerEntryOut(**defaults)


def test_running_balances_skip_pending_rows() -> None:
    pair = uuid4()
    approved = _entry(
        pair_id=pair,
        account_type="office",
        direction="debit",
        amount_pence=5000,
        is_approved=True,
    )
    pending = _entry(
        pair_id=pair,
        account_type="client",
        direction="credit",
        amount_pence=5000,
        description="Draft (pending approval)",
        is_approved=False,
        posted_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    balances = _running_balances([approved, pending])
    assert balances[str(approved.id)] == (-5000, 0)
    assert balances[str(pending.id)] == (None, None)


def test_entry_pending_from_legacy_description() -> None:
    row = _entry(description="Invoice INV-1 (pending approval)", is_approved=False)
    assert _entry_pending(row) is True
