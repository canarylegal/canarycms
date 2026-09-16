"""Portal branding helpers."""

from __future__ import annotations

from app.portal_branding import firm_display_name, portal_title
from app.models import FirmSettings


def test_portal_title_from_trading_name() -> None:
    firm = FirmSettings(id=1, trading_name="Example Solicitors")
    assert firm_display_name(firm) == "Example Solicitors"
    assert portal_title(firm) == "Example Solicitors Portal"


def test_portal_title_fallback() -> None:
    assert portal_title(None) == "Client Portal"


def test_normalize_portal_background_color() -> None:
    from app.portal_background import normalize_portal_background_color, portal_bg_contrast_ok

    assert normalize_portal_background_color(None) is None
    assert normalize_portal_background_color("") is None
    assert normalize_portal_background_color("  ") is None
    assert normalize_portal_background_color("#1e293b") == "#1E293B"
    assert normalize_portal_background_color("abc") == "#AABBCC"
    assert normalize_portal_background_color("#ABC") == "#AABBCC"
    assert portal_bg_contrast_ok("#1E293B") is True
    assert portal_bg_contrast_ok("#FFFFFF") is False
    try:
        normalize_portal_background_color("not-a-colour")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
