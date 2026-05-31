"""Normalize stored user appearance preferences."""

from __future__ import annotations

import re

from app.models import User
from app.schemas import UserAppearanceOut

DEFAULT_ACCENT = "#2563eb"
_HEX6 = re.compile(r"^#[0-9a-fA-F]{6}$")


def user_appearance_out(user: User) -> UserAppearanceOut:
    mode_raw = (user.appearance_mode or "light").strip().lower()
    mode = "dark" if mode_raw == "dark" else "light"
    accent = (user.appearance_accent or "").strip() or DEFAULT_ACCENT
    if not _HEX6.fullmatch(accent):
        accent = DEFAULT_ACCENT
    page_bg = (user.appearance_page_bg or "").strip()
    if page_bg and not _HEX6.fullmatch(page_bg):
        page_bg = ""
    font = (user.appearance_font or "").strip()
    return UserAppearanceOut(font=font, accent=accent, mode=mode, page_bg=page_bg)


def normalize_appearance_update(
    *,
    font: str,
    accent: str,
    mode: str,
    page_bg: str,
) -> tuple[str | None, str, str, str | None]:
    font_clean = font.strip() or None
    accent_clean = accent.strip() or DEFAULT_ACCENT
    if not _HEX6.fullmatch(accent_clean):
        raise ValueError("accent must be a 6-digit hex colour (#RRGGBB)")
    mode_clean = "dark" if (mode or "").strip().lower() == "dark" else "light"
    page_clean = page_bg.strip()
    if page_clean and not _HEX6.fullmatch(page_clean):
        raise ValueError("page_bg must be empty or a 6-digit hex colour (#RRGGBB)")
    return font_clean, accent_clean, mode_clean, page_clean or None
