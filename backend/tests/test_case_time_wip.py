"""Case time WIP billing helpers."""

from datetime import date

import pytest
from fastapi import HTTPException

from app.case_time_service import (
    format_time_invoice_description,
    time_entry_value_pence,
    validate_duration_minutes,
    wip_age_bucket,
)
from app.models import CaseTimeEntry, CaseTimeEntryStatus


def test_validate_duration_minutes_requires_six_minute_units() -> None:
    validate_duration_minutes(6)
    validate_duration_minutes(12)
    with pytest.raises(HTTPException):
        validate_duration_minutes(5)
    with pytest.raises(HTTPException):
        validate_duration_minutes(7)


def test_time_entry_value_pence() -> None:
    assert time_entry_value_pence(60, 30000) == 30000
    assert time_entry_value_pence(12, 30000) == 6000
    assert time_entry_value_pence(12, None) is None
    assert time_entry_value_pence(12, 0) is None


def test_wip_age_bucket() -> None:
    assert wip_age_bucket(0) == "0-30"
    assert wip_age_bucket(30) == "0-30"
    assert wip_age_bucket(31) == "31-90"
    assert wip_age_bucket(90) == "31-90"
    assert wip_age_bucket(91) == "90+"


def test_format_time_invoice_description() -> None:
    entry = CaseTimeEntry(
        work_date=date(2024, 6, 1),
        duration_minutes=30,
        description="Reviewed contract",
        status=CaseTimeEntryStatus.unbilled,
    )
    assert format_time_invoice_description(entry) == "2024-06-01 — Reviewed contract (0.5 hr)"
