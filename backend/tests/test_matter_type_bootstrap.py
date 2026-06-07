"""Matter type seed helpers."""

from __future__ import annotations

from app.matter_type_bootstrap import default_sub_menu_names_from_seed


def test_default_sub_menu_names_from_seed() -> None:
    raw = {
        "version": 1,
        "default_sub_menus": ["Events", "Finance", "Property", "Tasks"],
        "matter_types": [],
    }
    assert default_sub_menu_names_from_seed(raw) == ["Events", "Finance", "Property", "Tasks"]


def test_default_sub_menu_names_fallback() -> None:
    assert default_sub_menu_names_from_seed({}) == ["Events", "Finance", "Property", "Tasks"]
