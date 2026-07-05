"""Tests for quote case reference display."""

from __future__ import annotations

from app.case_reference import display_case_number, strip_case_number_prefix
from app.models import CaseStatus


def test_strip_case_number_prefix() -> None:
    assert strip_case_number_prefix("Q000123") == "000123"
    assert strip_case_number_prefix("q000123") == "000123"
    assert strip_case_number_prefix("000123") == "000123"


def test_display_case_number_quote() -> None:
    assert display_case_number("000123", CaseStatus.quote) == "Q000123"
    assert display_case_number("Q000123", CaseStatus.quote) == "Q000123"


def test_display_case_number_non_quote() -> None:
    assert display_case_number("000123", CaseStatus.open) == "000123"
    assert display_case_number("Q000123", CaseStatus.open) == "000123"
    assert display_case_number("000123", CaseStatus.quote_closed) == "000123"
