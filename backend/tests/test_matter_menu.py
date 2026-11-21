"""Run against migrated PostgreSQL in the isolated performance job as well as unit CI."""
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.matter_menu import menu_page, matter_type_options
from app.models import Case, CaseStatus, CaseSource, User


@pytest.mark.parametrize('cursor', ['bad', 'W10=', 'e30=', 'bnVsbA=='])
def test_invalid_cursor_is_a_client_error(cursor):
    with pytest.raises(HTTPException) as error:
        menu_page(Mock(), cursor=cursor)
    assert error.value.status_code == 400


def test_nul_search_is_rejected_before_query():
    db = Mock()
    with pytest.raises(HTTPException) as error:
        menu_page(db, q='a\x00b')
    assert error.value.status_code == 400
    db.execute.assert_not_called()


@pytest.fixture
def menu_fixture(db):
    # No commits: the db fixture rolls back all test-only changes.
    creator = db.scalar(select(User))
    assert creator is not None
    marker = 'menu-test-' + uuid.uuid4().hex
    source = CaseSource(id=uuid.uuid4(), name=marker+' Source', sort_order=0)
    db.add(source)
    db.flush()
    rows = []
    for i, label in enumerate(['alpha', 'Alpha', 'áccent', 'Zulu', '100%_literal', 'same', 'same', 'same']):
        row = Case(id=uuid.uuid4(), case_number=marker+str(i), title='Description '+label,
            client_name=marker+' '+label, status=CaseStatus.open, created_by=creator.id,
            fee_earner_user_id=creator.id, source_id=source.id,
            matter_head_type_name=marker, matter_sub_type_name='Subtype',
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        db.add(row); rows.append(row)
    db.flush()
    return marker, rows, creator


def test_all_sort_directions_ties_and_filter_options(db, menu_fixture):
    marker, expected, _ = menu_fixture
    for sort in ['reference', 'client', 'matter', 'feeEarner', 'status', 'source', 'created']:
        for direction in ['asc', 'desc']:
            found = []; cursor = None
            while True:
                page, cursor = menu_page(db, q=marker, sort=sort, direction=direction, limit=3, cursor=cursor)
                assert len(page) <= 3
                found.extend(c.id for c in page)
                if not cursor: break
                assert len(found) <= len(expected)
            assert len(found) == len(set(found)) == len(expected)
            assert set(found) == {row.id for row in expected}
    assert marker+' · Subtype' in matter_type_options(db)


def test_search_literals_labels_filter_override_and_quote_split(db, menu_fixture):
    marker, rows, user = menu_fixture
    rows[0].status = CaseStatus.closed
    rows[1].status = CaseStatus.quote
    rows[2].status = CaseStatus.quote_closed
    db.flush()
    def ids(**kwargs): return {c.id for c in menu_page(db, **kwargs)[0]}
    assert ids(q=marker+' 100%_literal') == {rows[4].id}
    assert ids(matter_types=[marker+' · Subtype'], statuses=[CaseStatus.closed]) == {rows[0].id}
    assert ids(matter_types=[marker+' · Subtype'], fee_earners=[uuid.uuid4()]) == set()
    assert ids(q=marker, statuses=[CaseStatus.archived], matter_types=['does not exist']) == {r.id for r in rows if r.status not in [CaseStatus.quote, CaseStatus.quote_closed]}
    assert ids(q=marker, menu='quotes') == {rows[1].id, rows[2].id}
    assert ids(q='Q'+rows[1].case_number, menu='quotes') == {rows[1].id}
    # Search includes displayed status and source; inactive staff are displayed as an em dash.
    assert rows[3].id in ids(q='Active '+user.display_name+' '+marker+' Source')
    user.is_active = False; db.flush()
    assert rows[3].id in ids(q='Active — '+marker+' Source')


def test_cursor_query_binding_and_deletion_at_boundary(db, menu_fixture):
    marker, rows, _ = menu_fixture
    first, cursor = menu_page(db, q=marker, sort='reference', direction='asc', limit=3)
    with pytest.raises(HTTPException): menu_page(db, q='different', cursor=cursor)
    boundary = first[-1]
    db.delete(boundary); db.flush()
    rest, _ = menu_page(db, q=marker, sort='reference', direction='asc', cursor=cursor)
    assert {r.id for r in first + rest} == {r.id for r in rows}
    assert len(first + rest) == len(rows)
