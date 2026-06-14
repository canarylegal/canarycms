"""Case time non-billable / nil-rate rules."""

import pytest
from fastapi import HTTPException

from app.case_time_service import resolve_non_billable, user_has_charge_rate
from app.models import User


def _user(rate: int | None) -> User:
    return User(email="a@b.c", display_name="Alice", charge_rate_pence_per_hour=rate)


def test_user_has_charge_rate() -> None:
    assert user_has_charge_rate(_user(30000))
    assert not user_has_charge_rate(_user(None))
    assert not user_has_charge_rate(_user(0))


def test_resolve_non_billable_requires_nil_when_no_rate() -> None:
    with pytest.raises(HTTPException):
        resolve_non_billable(non_billable=False, target_user=_user(None))
    assert resolve_non_billable(non_billable=True, target_user=_user(None)) is True


def test_resolve_non_billable_allows_optional_nil_with_rate() -> None:
    assert resolve_non_billable(non_billable=False, target_user=_user(25000)) is False
    assert resolve_non_billable(non_billable=True, target_user=_user(25000)) is True
