"""Bounded document streams, ordered by parent group, with independent folder metadata."""
from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.orm import aliased

from app.list_search import _ilike_pattern, reject_search_nul
from app.models import File, User


def visible(model, case_id):
    return and_(model.case_id == case_id, model.oo_compose_pending.is_(False))


def sort_value(file, owner, sort):
    if sort == 'size':
        return file.size_bytes
    if sort == 'created':
        mail = or_(func.lower(file.original_filename).endswith('.eml'),
                   func.lower(file.mime_type).contains('rfc822'),
                   func.trim(func.coalesce(file.outlook_graph_message_id, '')) != '',
                   func.trim(func.coalesce(file.outlook_web_link, '')) != '')
        return case((and_(file.parent_file_id.is_(None), mail, file.source_mail_date.isnot(None)), file.source_mail_date), else_=file.created_at)
    if sort == 'user':
        value = case((file.uploaded_via_portal.is_(True), 'Portal'),
                     else_=func.coalesce(owner.initials, owner.display_name, owner.email, '—'))
    else:
        value = file.original_filename
    return value.collate('und-x-icu')


def document_page(db, case_id, *, folder='', q='', sort='created', direction='desc', limit=100, cursor=None):
    q = q.strip().lower()
    reject_search_nul(q)
    reject_search_nul(folder)
    root, owner, root_owner = aliased(File), aliased(User), aliased(User)
    child = File.parent_file_id.isnot(None)
    # Only the immediate children displayed by the existing document browser are in this stream.
    root_id = func.coalesce(File.parent_file_id, File.id)
    stmt = (select(File, owner.display_name, owner.email, owner.initials)
        .join(owner, owner.id == File.owner_id)
        .join(root, and_(root.id == root_id, visible(root, case_id), root.parent_file_id.is_(None), root.category != 'system', root.folder_path == folder))
        .join(root_owner, root_owner.id == root.owner_id)
        .where(visible(File, case_id), File.category != 'system', File.folder_path == folder))
    if q:
        # Recursive closure includes parents, siblings and descendants, including matches in
        # another folder. UNION (not UNION ALL) terminates even for corrupt cyclic links.
        related = select(File.id, File.parent_file_id).where(visible(File, case_id), or_(
            func.lower(File.original_filename).like(_ilike_pattern(q), escape='\\'),
            func.lower(File.source_mail_from_name).like(_ilike_pattern(q), escape='\\'),
            func.lower(File.source_mail_from_email).like(_ilike_pattern(q), escape='\\'),
        )).cte('related_documents', recursive=True)
        neighbor = aliased(File)
        related = related.union(select(neighbor.id, neighbor.parent_file_id).join(related,
            or_(neighbor.id == related.c.parent_file_id, neighbor.parent_file_id == related.c.id)).where(visible(neighbor, case_id)))
        stmt = stmt.where(File.id.in_(select(related.c.id)))
    keys = [case((root.is_pinned.is_(True), 0), else_=1), sort_value(root, root_owner, sort),
            root.created_at, root.id, case((child, 1), else_=0), sort_value(File, owner, sort), File.created_at, File.id]
    directions = ['asc', direction, 'desc', 'asc', 'asc', direction, 'desc', 'asc']
    signature = hashlib.sha256(json.dumps([str(case_id), folder, q, sort, direction]).encode()).hexdigest()
    if cursor:
        try:
            data = json.loads(base64.urlsafe_b64decode(cursor))
            if data['query'] != signature or len(data['keys']) != len(keys): raise ValueError()
            values = data['keys']
            for i in (2, 6): values[i] = datetime.fromisoformat(values[i])
            for i in (3, 7): values[i] = uuid.UUID(values[i])
            for i in (0, 4):
                if type(values[i]) is not int or values[i] not in (0, 1): raise ValueError()
            for i in (1, 5):
                if sort == 'created': values[i] = datetime.fromisoformat(values[i])
                elif sort == 'size':
                    if type(values[i]) is not int: raise ValueError()
                elif not isinstance(values[i], str): raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise HTTPException(400, 'Invalid document cursor. Refresh the list.') from None
        stmt = stmt.where(or_(*[and_(*[keys[j] == values[j] for j in range(i)],
            keys[i] > values[i] if directions[i] == 'asc' else keys[i] < values[i]) for i in range(len(keys))]))
    stmt = stmt.add_columns(*[key.label(f'page_key_{i}') for i, key in enumerate(keys)]).order_by(
        *[key.asc() if d == 'asc' else key.desc() for key, d in zip(keys, directions)]).limit(limit + 1)
    result = db.execute(stmt).all()
    next_cursor = None
    if len(result) > limit:
        next_cursor = base64.urlsafe_b64encode(json.dumps({'query': signature, 'keys': [
            v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, uuid.UUID) else v
            for v in result[limit - 1][4:]]}).encode()).decode()
    return [tuple(row[:4]) for row in result[:limit]], [row[4] == 0 for row in result[:limit]], next_cursor


def folder_metadata(db, case_id):
    rows = db.execute(select(File.folder_path,
        func.count().filter(and_(File.category != 'system', File.parent_file_id.is_(None))),
        func.count().filter(File.category != 'system'))
        .where(visible(File, case_id)).group_by(File.folder_path)).all()
    paths, counts, populated = set(), {}, set()
    for path, roots, count in rows:
        path = (path or '').strip()
        counts[path] = roots
        if count: populated.add(path)
        parts = [p for p in path.split('/') if p]
        for i in range(1, len(parts) + 1): paths.add('/'.join(parts[:i]))
    child_names = {}
    for other in populated:
        parts = other.split('/')
        for i in range(1, len(parts)):
            child_names.setdefault('/'.join(parts[:i]), set()).add(parts[i])
    summaries = {}
    for path in paths:
        children = child_names.get(path, set())
        count = counts.get(path, 0)
        summaries[path] = f"{count} {'item' if count == 1 else 'items'}, {len(children)} {'subfolder' if len(children) == 1 else 'subfolders'}"
    return {'paths': sorted(paths), 'summaries': summaries}
