"""User UI preference normalization."""

from app.user_ui_preferences import (
    MAIN_MENU_COLUMN_WIDTHS_DEFAULT,
    UserUiPreferencesOut,
    UserUiPreferencesPatch,
    merge_ui_preferences_patch,
    ui_preferences_is_default,
    user_ui_preferences_out,
)


def test_defaults_when_empty() -> None:
    prefs = user_ui_preferences_out(None)
    assert prefs.calendar_view == "dayGridMonth"
    assert prefs.tasks_menu_layout == "list"
    assert prefs.main_menu_column_widths == []
    assert ui_preferences_is_default(prefs)


def test_merge_partial_patch() -> None:
    merged = merge_ui_preferences_patch(
        {"calendar_view": "dayGridMonth"},
        UserUiPreferencesPatch(
            tasks_menu_layout="kanban",
            tasks_menu_sort_dir="desc",
            main_menu_search="smith",
            calendar_selected_calendar_ids=["abc-123"],
        ),
    )
    out = user_ui_preferences_out(merged)
    assert out.tasks_menu_layout == "kanban"
    assert out.tasks_menu_sort_dir == "desc"
    assert out.main_menu_search == "smith"
    assert out.calendar_selected_calendar_ids == ["abc-123"]


def test_invalid_values_fall_back_to_defaults() -> None:
    out = user_ui_preferences_out(
        {
            "calendar_view": "not-a-view",
            "tasks_menu_layout": "grid",
            "main_menu_sort_key": "invalid",
            "main_menu_filter_case_status": "bogus",
            "main_menu_column_widths": [1, 2],
            "contacts_sort_key": "address",
        }
    )
    assert out.calendar_view == "dayGridMonth"
    assert out.tasks_menu_layout == "list"
    assert out.main_menu_sort_key == "created"
    assert out.main_menu_filter_case_status == ""
    assert out.main_menu_column_widths == []
    assert out.contacts_sort_key == "name"


def test_column_widths_clamped() -> None:
    raw = {"main_menu_column_widths": [10, 5000, 300, 180, 100]}
    out = user_ui_preferences_out(raw)
    assert out.main_menu_column_widths[0] == 48
    assert out.main_menu_column_widths[1] == 2000
    assert out.tasks_menu_column_widths == []
    assert out.contacts_column_widths == []


def test_legacy_auto_column_widths_treated_as_unset() -> None:
    out = user_ui_preferences_out({"main_menu_column_widths": MAIN_MENU_COLUMN_WIDTHS_DEFAULT})
    assert out.main_menu_column_widths == []
