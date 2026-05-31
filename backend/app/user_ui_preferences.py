"""Normalize and merge per-user UI preferences (layout, filters, column widths)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

CalendarView = Literal["dayGridMonth", "timeGridWeek", "timeGridDay", "listWeek"]
TaskLayout = Literal["list", "kanban"]
TaskSortKey = Literal["reference", "client", "matter", "task", "date", "assigned", "priority"]
MainMenuSortKey = Literal["reference", "client", "matter", "feeEarner", "status", "created"]
ContactsSortKey = Literal["name", "type", "email", "phone"]
CaseStatusFilter = Literal["", "open", "closed", "archived", "quote", "post_completion"]
SortDir = Literal["asc", "desc"]

_CALENDAR_VIEWS = frozenset({"dayGridMonth", "timeGridWeek", "timeGridDay", "listWeek"})
_TASK_LAYOUTS = frozenset({"list", "kanban"})
_TASK_SORT_KEYS = frozenset({"reference", "client", "matter", "task", "date", "assigned", "priority"})
_MAIN_MENU_SORT_KEYS = frozenset({"reference", "client", "matter", "feeEarner", "status", "created"})
_CONTACTS_SORT_KEYS = frozenset({"name", "type", "email", "phone"})
_CASE_STATUS_FILTERS = frozenset({"", "open", "closed", "archived", "quote", "post_completion"})
_SORT_DIRS = frozenset({"asc", "desc"})

MAIN_MENU_COLUMN_WIDTHS_DEFAULT = [110, 240, 300, 180, 100]
TASKS_MENU_COLUMN_WIDTHS_DEFAULT = [90, 66, 90, 210, 300, 183, 73]
CONTACTS_COLUMN_WIDTHS_DEFAULT = [270, 210, 210, 210]

_LEGACY_AUTO_MAIN_MENU_COLUMN_WIDTHS = MAIN_MENU_COLUMN_WIDTHS_DEFAULT
_LEGACY_AUTO_TASKS_MENU_COLUMN_WIDTHS = TASKS_MENU_COLUMN_WIDTHS_DEFAULT
_LEGACY_AUTO_CONTACTS_COLUMN_WIDTHS = CONTACTS_COLUMN_WIDTHS_DEFAULT

_SEARCH_MAX_LEN = 500


class UserUiPreferencesOut(BaseModel):
    calendar_view: CalendarView = "dayGridMonth"
    case_calendar_view: CalendarView = "dayGridMonth"
    tasks_menu_layout: TaskLayout = "list"
    case_tasks_layout: TaskLayout = "list"
    tasks_menu_sort_key: TaskSortKey = "priority"
    tasks_menu_sort_dir: SortDir = "asc"
    case_tasks_sort_key: TaskSortKey = "priority"
    case_tasks_sort_dir: SortDir = "asc"
    main_menu_sort_key: MainMenuSortKey = "created"
    main_menu_sort_dir: SortDir = "desc"
    main_menu_search: str = ""
    main_menu_filter_matter_type: str = ""
    main_menu_filter_fee_earner_user_id: str = ""
    main_menu_filter_case_status: CaseStatusFilter = ""
    main_menu_filter_matter_types: list[str] = Field(default_factory=list)
    main_menu_filter_fee_earner_user_ids: list[str] = Field(default_factory=list)
    main_menu_filter_case_statuses: list[CaseStatusFilter] = Field(default_factory=list)
    tasks_menu_search: str = ""
    tasks_menu_filter_matter_type: str = ""
    contacts_search: str = ""
    contacts_sort_key: ContactsSortKey = "name"
    contacts_sort_dir: SortDir = "asc"
    calendar_selected_calendar_ids: list[str] = Field(default_factory=list)
    main_menu_column_widths: list[int] = Field(default_factory=list)
    tasks_menu_column_widths: list[int] = Field(default_factory=list)
    contacts_column_widths: list[int] = Field(default_factory=list)


class UserUiPreferencesPatch(BaseModel):
    calendar_view: CalendarView | None = None
    case_calendar_view: CalendarView | None = None
    tasks_menu_layout: TaskLayout | None = None
    case_tasks_layout: TaskLayout | None = None
    tasks_menu_sort_key: TaskSortKey | None = None
    tasks_menu_sort_dir: SortDir | None = None
    case_tasks_sort_key: TaskSortKey | None = None
    case_tasks_sort_dir: SortDir | None = None
    main_menu_sort_key: MainMenuSortKey | None = None
    main_menu_sort_dir: SortDir | None = None
    main_menu_search: str | None = None
    main_menu_filter_matter_type: str | None = None
    main_menu_filter_fee_earner_user_id: str | None = None
    main_menu_filter_case_status: CaseStatusFilter | None = None
    main_menu_filter_matter_types: list[str] | None = None
    main_menu_filter_fee_earner_user_ids: list[str] | None = None
    main_menu_filter_case_statuses: list[CaseStatusFilter] | None = None
    tasks_menu_search: str | None = None
    tasks_menu_filter_matter_type: str | None = None
    contacts_search: str | None = None
    contacts_sort_key: ContactsSortKey | None = None
    contacts_sort_dir: SortDir | None = None
    calendar_selected_calendar_ids: list[str] | None = None
    main_menu_column_widths: list[int] | None = None
    tasks_menu_column_widths: list[int] | None = None
    contacts_column_widths: list[int] | None = None


def _pick_str(raw: Any, allowed: frozenset[str], default: str) -> str:
    if isinstance(raw, str) and raw in allowed:
        return raw
    return default


def _pick_search(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    return raw.strip()[:_SEARCH_MAX_LEN]


def _pick_filter_text(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    return raw.strip()[:200]


def _pick_fee_earner_id(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if not s:
        return ""
    try:
        uuid.UUID(s)
    except ValueError:
        return ""
    return s


def _normalize_id_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _clamp_widths(raw: Any, expected: int) -> list[int] | None:
    if not isinstance(raw, list) or len(raw) != expected:
        return None
    out: list[int] = []
    for item in raw:
        if not isinstance(item, (int, float)):
            return None
        try:
            w = int(item)
        except (TypeError, ValueError):
            return None
        out.append(max(48, min(2000, w)))
    return out


def _stored_column_widths(raw: Any, expected: int, legacy_auto: list[int]) -> list[int]:
    clamped = _clamp_widths(raw, expected)
    if clamped is None:
        return []
    if clamped == legacy_auto:
        return []
    return clamped


def _pick_filter_text_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        s = _pick_filter_text(item)
        if s and s not in out:
            out.append(s)
    return out


def _pick_fee_earner_id_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        s = _pick_fee_earner_id(item)
        if s and s not in out:
            out.append(s)
    return out


def _pick_case_status_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item in _CASE_STATUS_FILTERS and item != "":
            if item not in out:
                out.append(item)
    return out


def _legacy_main_menu_matter_types(data: dict[str, Any]) -> list[str]:
    from_list = _pick_filter_text_list(data.get("main_menu_filter_matter_types"))
    if from_list:
        return from_list
    one = _pick_filter_text(data.get("main_menu_filter_matter_type"))
    return [one] if one else []


def _legacy_main_menu_fee_earner_ids(data: dict[str, Any]) -> list[str]:
    from_list = _pick_fee_earner_id_list(data.get("main_menu_filter_fee_earner_user_ids"))
    if from_list:
        return from_list
    one = _pick_fee_earner_id(data.get("main_menu_filter_fee_earner_user_id"))
    return [one] if one else []


def _legacy_main_menu_case_statuses(data: dict[str, Any]) -> list[str]:
    from_list = _pick_case_status_list(data.get("main_menu_filter_case_statuses"))
    if from_list:
        return from_list
    one = _pick_str(data.get("main_menu_filter_case_status"), _CASE_STATUS_FILTERS, "")
    return [one] if one else []


def user_ui_preferences_out(stored: dict[str, Any] | None) -> UserUiPreferencesOut:
    data = stored if isinstance(stored, dict) else {}
    return UserUiPreferencesOut(
        calendar_view=_pick_str(data.get("calendar_view"), _CALENDAR_VIEWS, "dayGridMonth"),  # type: ignore[arg-type]
        case_calendar_view=_pick_str(data.get("case_calendar_view"), _CALENDAR_VIEWS, "dayGridMonth"),  # type: ignore[arg-type]
        tasks_menu_layout=_pick_str(data.get("tasks_menu_layout"), _TASK_LAYOUTS, "list"),  # type: ignore[arg-type]
        case_tasks_layout=_pick_str(data.get("case_tasks_layout"), _TASK_LAYOUTS, "list"),  # type: ignore[arg-type]
        tasks_menu_sort_key=_pick_str(data.get("tasks_menu_sort_key"), _TASK_SORT_KEYS, "priority"),  # type: ignore[arg-type]
        tasks_menu_sort_dir=_pick_str(data.get("tasks_menu_sort_dir"), _SORT_DIRS, "asc"),  # type: ignore[arg-type]
        case_tasks_sort_key=_pick_str(data.get("case_tasks_sort_key"), _TASK_SORT_KEYS, "priority"),  # type: ignore[arg-type]
        case_tasks_sort_dir=_pick_str(data.get("case_tasks_sort_dir"), _SORT_DIRS, "asc"),  # type: ignore[arg-type]
        main_menu_sort_key=_pick_str(data.get("main_menu_sort_key"), _MAIN_MENU_SORT_KEYS, "created"),  # type: ignore[arg-type]
        main_menu_sort_dir=_pick_str(data.get("main_menu_sort_dir"), _SORT_DIRS, "desc"),  # type: ignore[arg-type]
        main_menu_search=_pick_search(data.get("main_menu_search")),
        main_menu_filter_matter_type=_pick_filter_text(data.get("main_menu_filter_matter_type")),
        main_menu_filter_fee_earner_user_id=_pick_fee_earner_id(data.get("main_menu_filter_fee_earner_user_id")),
        main_menu_filter_case_status=_pick_str(data.get("main_menu_filter_case_status"), _CASE_STATUS_FILTERS, ""),  # type: ignore[arg-type]
        main_menu_filter_matter_types=_legacy_main_menu_matter_types(data),
        main_menu_filter_fee_earner_user_ids=_legacy_main_menu_fee_earner_ids(data),
        main_menu_filter_case_statuses=_legacy_main_menu_case_statuses(data),  # type: ignore[arg-type]
        tasks_menu_search=_pick_search(data.get("tasks_menu_search")),
        tasks_menu_filter_matter_type=_pick_filter_text(data.get("tasks_menu_filter_matter_type")),
        contacts_search=_pick_search(data.get("contacts_search")),
        contacts_sort_key=_pick_str(data.get("contacts_sort_key"), _CONTACTS_SORT_KEYS, "name"),  # type: ignore[arg-type]
        contacts_sort_dir=_pick_str(data.get("contacts_sort_dir"), _SORT_DIRS, "asc"),  # type: ignore[arg-type]
        calendar_selected_calendar_ids=_normalize_id_list(data.get("calendar_selected_calendar_ids")),
        main_menu_column_widths=_stored_column_widths(
            data.get("main_menu_column_widths"),
            len(MAIN_MENU_COLUMN_WIDTHS_DEFAULT),
            _LEGACY_AUTO_MAIN_MENU_COLUMN_WIDTHS,
        ),
        tasks_menu_column_widths=_stored_column_widths(
            data.get("tasks_menu_column_widths"),
            len(TASKS_MENU_COLUMN_WIDTHS_DEFAULT),
            _LEGACY_AUTO_TASKS_MENU_COLUMN_WIDTHS,
        ),
        contacts_column_widths=_stored_column_widths(
            data.get("contacts_column_widths"),
            len(CONTACTS_COLUMN_WIDTHS_DEFAULT),
            _LEGACY_AUTO_CONTACTS_COLUMN_WIDTHS,
        ),
    )


def merge_ui_preferences_patch(
    stored: dict[str, Any] | None,
    patch: UserUiPreferencesPatch,
) -> dict[str, Any]:
    merged = user_ui_preferences_out(stored).model_dump()
    updates = patch.model_dump(exclude_unset=True)
    if "main_menu_search" in updates and updates["main_menu_search"] is not None:
        updates["main_menu_search"] = _pick_search(updates["main_menu_search"])
    if "tasks_menu_search" in updates and updates["tasks_menu_search"] is not None:
        updates["tasks_menu_search"] = _pick_search(updates["tasks_menu_search"])
    if "contacts_search" in updates and updates["contacts_search"] is not None:
        updates["contacts_search"] = _pick_search(updates["contacts_search"])
    if "main_menu_filter_matter_type" in updates and updates["main_menu_filter_matter_type"] is not None:
        updates["main_menu_filter_matter_type"] = _pick_filter_text(updates["main_menu_filter_matter_type"])
    if "tasks_menu_filter_matter_type" in updates and updates["tasks_menu_filter_matter_type"] is not None:
        updates["tasks_menu_filter_matter_type"] = _pick_filter_text(updates["tasks_menu_filter_matter_type"])
    if "main_menu_filter_fee_earner_user_id" in updates and updates["main_menu_filter_fee_earner_user_id"] is not None:
        updates["main_menu_filter_fee_earner_user_id"] = _pick_fee_earner_id(
            updates["main_menu_filter_fee_earner_user_id"]
        )
    if "main_menu_filter_matter_types" in updates and updates["main_menu_filter_matter_types"] is not None:
        updates["main_menu_filter_matter_types"] = _pick_filter_text_list(updates["main_menu_filter_matter_types"])
    if "main_menu_filter_fee_earner_user_ids" in updates and updates["main_menu_filter_fee_earner_user_ids"] is not None:
        updates["main_menu_filter_fee_earner_user_ids"] = _pick_fee_earner_id_list(
            updates["main_menu_filter_fee_earner_user_ids"]
        )
    if "main_menu_filter_case_statuses" in updates and updates["main_menu_filter_case_statuses"] is not None:
        updates["main_menu_filter_case_statuses"] = _pick_case_status_list(updates["main_menu_filter_case_statuses"])
    if "calendar_selected_calendar_ids" in updates and updates["calendar_selected_calendar_ids"] is not None:
        updates["calendar_selected_calendar_ids"] = _normalize_id_list(updates["calendar_selected_calendar_ids"])
    if "main_menu_column_widths" in updates and updates["main_menu_column_widths"] is not None:
        clamped = _clamp_widths(updates["main_menu_column_widths"], len(MAIN_MENU_COLUMN_WIDTHS_DEFAULT))
        if clamped is not None:
            updates["main_menu_column_widths"] = clamped
        else:
            updates.pop("main_menu_column_widths", None)
    if "tasks_menu_column_widths" in updates and updates["tasks_menu_column_widths"] is not None:
        clamped = _clamp_widths(updates["tasks_menu_column_widths"], len(TASKS_MENU_COLUMN_WIDTHS_DEFAULT))
        if clamped is not None:
            updates["tasks_menu_column_widths"] = clamped
        else:
            updates.pop("tasks_menu_column_widths", None)
    if "contacts_column_widths" in updates and updates["contacts_column_widths"] is not None:
        clamped = _clamp_widths(updates["contacts_column_widths"], len(CONTACTS_COLUMN_WIDTHS_DEFAULT))
        if clamped is not None:
            updates["contacts_column_widths"] = clamped
        else:
            updates.pop("contacts_column_widths", None)
    merged.update(updates)
    return user_ui_preferences_out(merged).model_dump()


def ui_preferences_is_default(prefs: UserUiPreferencesOut) -> bool:
    return prefs == UserUiPreferencesOut()
