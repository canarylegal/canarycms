"""Case time entry validation."""

import pytest
from fastapi import HTTPException

from app.case_time_service import time_entry_value_pence, validate_duration_minutes


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
