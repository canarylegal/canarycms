"""Property address merge codes, including matter-title fallback."""

from app.docx_util.merge_fields import (
    _address_lines_from_matter_title,
    _join_property_address_one_line,
)


def test_address_lines_from_matter_title_strips_conveyancing_prefix() -> None:
    lines = _address_lines_from_matter_title(
        "Sale of 847 High Street, First Floor, Glasgow, South Yorkshire, OX1 2LY, United Kingdom"
    )
    assert lines[0] == "847 High Street"
    assert lines[-1] == "United Kingdom"
    assert _join_property_address_one_line(lines).startswith("847 High Street, First Floor")


def test_address_lines_from_matter_title_ignores_unrelated_titles() -> None:
    assert _address_lines_from_matter_title("General advice") == []
    assert _address_lines_from_matter_title("") == []
