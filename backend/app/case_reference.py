"""Case reference display helpers — storage stays numeric; quotes show a Q prefix."""

from __future__ import annotations

from app.models import CaseStatus


def strip_case_number_prefix(case_number: str) -> str:
    """Return the stored reference without a leading Q (case-insensitive)."""
    s = (case_number or "").strip()
    if len(s) > 1 and s[0].upper() == "Q" and s[1].isdigit():
        return s[1:]
    return s


def display_case_number(case_number: str, status: CaseStatus | str) -> str:
    """Format a matter reference for UI: Q prefix while status is quote only."""
    raw = strip_case_number_prefix(case_number)
    if not raw:
        return raw
    st = status.value if isinstance(status, CaseStatus) else str(status)
    if st == CaseStatus.quote.value:
        return f"Q{raw}"
    return raw
