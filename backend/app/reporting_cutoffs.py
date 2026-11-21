"""Shared UTC recognition rules for financial reports and reconciliations."""
from sqlalchemy import func
from app.models import LedgerEntry


def ledger_effective_at():
    # Legacy rows without approval evidence retain their recorded posting date.
    return func.coalesce(LedgerEntry.recognised_at, LedgerEntry.posted_at)
