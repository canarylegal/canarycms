"""Validate matter links without trusting client-supplied CalDAV locations."""
import uuid
from urllib.parse import quote, unquote, urlsplit
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import User, UserCalendar, UserCalendarShare
from app.calendar_service import get_calendar_for_owner, resolve_calendar_access, require_write
from app.radicale_calendar import _internal_base, ref_to_href, href_to_ref, load_event_on_principal


def canonical_event_ref(ref: str) -> str:
    try:
        url = urlsplit(ref_to_href(ref))
        base = urlsplit(_internal_base())
        if (url.scheme, url.netloc) != (base.scheme, base.netloc) or url.query or url.fragment:
            raise ValueError()
        prefix = base.path.rstrip('/') + '/'
        if not url.path.startswith(prefix):
            raise ValueError()
        parts = [unquote(p) for p in url.path[len(prefix):].split('/')]
        if len(parts) != 3 or any(not p or p in ('.', '..') or '/' in p or '\\' in p or any(ord(c)<32 for c in p) for p in parts):
            raise ValueError()
        parts[0] = str(uuid.UUID(parts[0]))
        href = _internal_base() + '/' + '/'.join(quote(p, safe='@-._~') for p in parts)
        return href_to_ref(href)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise HTTPException(400, 'Invalid calendar event reference') from exc


def authorize_event_link(db: Session, actor_user_id: uuid.UUID, ref: str) -> str:
    canonical = canonical_event_ref(ref)
    href = ref_to_href(canonical)
    base_path = urlsplit(_internal_base()).path.rstrip('/') + '/'
    owner, slug, _ = [unquote(p) for p in urlsplit(href).path[len(base_path):].split('/')]
    calendar = get_calendar_for_owner(db, uuid.UUID(owner), slug)
    if calendar is None:
        raise HTTPException(404, 'Calendar not found')
    # Serialize competing links to this calendar, including two different matter rows.
    db.execute(select(UserCalendar).where(UserCalendar.id == calendar.id).with_for_update()).scalar_one()
    actor = db.get(User, actor_user_id)
    if actor is None or not actor.is_active:
        raise HTTPException(403, 'Calendar access denied')
    db.execute(select(UserCalendarShare).where(UserCalendarShare.calendar_id == calendar.id,
        UserCalendarShare.grantee_user_id == actor_user_id).with_for_update()).scalars().all()
    access = resolve_calendar_access(db, actor, calendar.id)
    require_write(access)
    if not access.dav_user.caldav_password_enc:
        raise HTTPException(409, 'Calendar is unavailable')
    load_event_on_principal(access.dav_user, href)
    return canonical
