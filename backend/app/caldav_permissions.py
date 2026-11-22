"""Live CalDAV authorization from the same calendar grants used by the GUI."""
import uuid
from sqlalchemy.orm import Session
from app.models import User
from app.calendar_service import list_accessible_calendars


def calendar_rights(db: Session, username: str, path: str, method: str, request_path: str) -> str:
    try:
        user_id = uuid.UUID(username)
    except ValueError:
        return ""
    user = db.get(User, user_id)
    if not user or not user.is_active or not user.caldav_password_enc:
        return ""
    parts = path.strip('/').split('/') if path.strip('/') else []
    if any(p in ('.', '..', '') for p in parts) or len(parts) > 2:
        return ""
    if not parts:
        return "R"
    if parts[0] == str(user.id):
        return "RW" if len(parts) == 1 else "rw"
    # No role/admin bypass: another user's personal calendar is private too.
    accessible = [a for a in list_accessible_calendars(db, user)
                  if str(a.calendar.owner_user_id) == parts[0]
                  and a.dav_user.is_active and a.dav_user.caldav_password_enc]
    if len(parts) == 1:
        return "R" if accessible else ""
    access = next((a for a in accessible if a.calendar.radicale_slug == parts[1]), None)
    if not access:
        return ""
    result = "rw" if access.permission == "write" else "r"
    # A GUI editor can change events, not delete/rename the calendar or its
    # properties. Radicale 3.1 otherwise uses the same 'w' bit for both.
    if method not in ('GET', 'HEAD', 'OPTIONS', 'PROPFIND', 'REPORT'):
        target = request_path.strip('/').split('/')
        if method not in ('PUT', 'DELETE', 'MOVE') or len(target) != 3 or any(p in ('', '.', '..') for p in target):
            result = result.replace('w', '')
    return result
