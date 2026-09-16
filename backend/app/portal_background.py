"""Portal background colour (#RRGGBB) helpers."""

from __future__ import annotations

import re

_HEX6 = re.compile(r"^#([0-9A-Fa-f]{6})$")
_HEX3 = re.compile(r"^#([0-9A-Fa-f]{3})$")

# Default portal canvas when firm has not set a custom colour (matches local-modern chrome).
DEFAULT_PORTAL_BACKGROUND = "#1e293b"


def normalize_portal_background_color(raw: str | None) -> str | None:
    """Return canonical ``#RRGGBB`` or ``None`` for default / empty.

    Accepts ``#RGB`` or ``#RRGGBB`` (optional leading/trailing space). Empty clears to default.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if not s.startswith("#"):
        s = f"#{s}"
    m6 = _HEX6.match(s)
    if m6:
        return f"#{m6.group(1).upper()}"
    m3 = _HEX3.match(s)
    if m3:
        a, b, c = m3.group(1)
        return f"#{a}{a}{b}{b}{c}{c}".upper()
    raise ValueError("Portal background colour must be a hex value such as #1E293B.")


def portal_background_color(firm) -> str | None:
    """Configured solid background, or ``None`` when the product default should apply."""
    if firm is None:
        return None
    raw = getattr(firm, "portal_background_color", None)
    if not raw:
        return None
    try:
        return normalize_portal_background_color(raw)
    except ValueError:
        return None


def _srgb_channel(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    h = normalize_portal_background_color(hex_color)
    if h is None:
        h = DEFAULT_PORTAL_BACKGROUND
    r = int(h[1:3], 16)
    g = int(h[3:5], 16)
    b = int(h[5:7], 16)
    return 0.2126 * _srgb_channel(r) + 0.7152 * _srgb_channel(g) + 0.0722 * _srgb_channel(b)


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    l1 = relative_luminance(hex_a)
    l2 = relative_luminance(hex_b)
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


def portal_bg_contrast_ok(bg_hex: str, *, against: str = "#F8FAFC", min_ratio: float = 4.5) -> bool:
    """True when brand title / subtitle light ink remains readable on ``bg_hex``."""
    try:
        return contrast_ratio(bg_hex, against) >= min_ratio
    except ValueError:
        return False
