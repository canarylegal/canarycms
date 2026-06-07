"""Tests for server-side contact and case list search."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from sqlalchemy import JSON, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.list_search import search_cases, search_contacts
from app.models import Case, CaseLockMode, CaseStatus, Contact, ContactType, User


def _session(*tables) -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in tables:
        table.create(engine)
    return sessionmaker(bind=engine)()


def _case_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    pref_col = User.__table__.c.ui_preferences
    original_type = pref_col.type
    pref_col.type = JSON()
    try:
        User.__table__.create(engine)
        Case.__table__.create(engine)
    finally:
        pref_col.type = original_type
    return sessionmaker(bind=engine)()


def test_search_contacts_matches_name_email_and_filters() -> None:
    db = _session(Contact.__table__)
    db.add(
        Contact(
            id=uuid.uuid4(),
            type=ContactType.person,
            name="Alice Smith",
            email="alice@example.com",
            phone="01111111111",
        )
    )
    db.add(
        Contact(
            id=uuid.uuid4(),
            type=ContactType.organisation,
            name="Beta Ltd",
            email=None,
            phone="02222222222",
        )
    )
    db.commit()

    by_name = search_contacts(db, q="smith")
    assert len(by_name) == 1
    assert by_name[0].name == "Alice Smith"

    by_email = search_contacts(db, q="alice@")
    assert len(by_email) == 1

    org_only = search_contacts(db, q="beta", type_filter=ContactType.organisation)
    assert len(org_only) == 1
    assert org_only[0].name == "Beta Ltd"

    has_phone = search_contacts(db, has_phone=True)
    assert len(has_phone) == 2

    no_email = search_contacts(db, has_email=False)
    assert len(no_email) == 1
    assert no_email[0].name == "Beta Ltd"


def test_search_contacts_empty_query_returns_all_ordered_by_name() -> None:
    db = _session(Contact.__table__)
    db.add(Contact(id=uuid.uuid4(), type=ContactType.person, name="Zara"))
    db.add(Contact(id=uuid.uuid4(), type=ContactType.person, name="Aaron"))
    db.commit()

    rows = search_contacts(db)
    assert [c.name for c in rows] == ["Aaron", "Zara"]


def test_search_cases_matches_and_respects_access() -> None:
    db = _case_session()
    actor_id = uuid.uuid4()
    actor = User(
        id=actor_id,
        email="u@example.com",
        initials="UU",
        display_name="Test User",
        password_hash="x",
    )
    accessible = Case(
        id=uuid.uuid4(),
        case_number="847/2024",
        title="Purchase of 1 High Street",
        client_name="Smith",
        fee_earner_user_id=actor_id,
        created_by=actor_id,
        lock_mode=CaseLockMode.none,
    )
    hidden = Case(
        id=uuid.uuid4(),
        case_number="999/2024",
        title="Secret matter",
        client_name="Hidden",
        fee_earner_user_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        lock_mode=CaseLockMode.allow_list,
    )
    db.add(accessible)
    db.add(hidden)
    db.commit()

    def _access(case_id: uuid.UUID, user: User, session: Session) -> Case | None:
        case = session.get(Case, case_id)
        if case is None:
            return None
        return case if case.case_number != "999/2024" else None

    with patch("app.list_search.get_case_if_accessible", side_effect=_access):
        matches = search_cases(db, actor, q="847")
        assert len(matches) == 1
        assert matches[0].case_number == "847/2024"

        by_client = search_cases(db, actor, q="smith")
        assert len(by_client) == 1

        denied = search_cases(db, actor, q="999")
        assert denied == []


def test_search_cases_status_filter() -> None:
    db = _case_session()
    actor_id = uuid.uuid4()
    actor = User(
        id=actor_id,
        email="u@example.com",
        initials="UU",
        display_name="Test User",
        password_hash="x",
    )
    db.add(
        Case(
            id=uuid.uuid4(),
            case_number="100/2024",
            title="Open matter",
            fee_earner_user_id=actor_id,
            created_by=actor_id,
            status=CaseStatus.open,
            lock_mode=CaseLockMode.none,
        )
    )
    db.add(
        Case(
            id=uuid.uuid4(),
            case_number="101/2024",
            title="Quote matter",
            fee_earner_user_id=actor_id,
            created_by=actor_id,
            status=CaseStatus.quote,
            lock_mode=CaseLockMode.none,
        )
    )
    db.commit()

    with patch("app.list_search.get_case_if_accessible", side_effect=lambda cid, _u, session: session.get(Case, cid)):
        quotes = search_cases(db, actor, q="matter", status_filter=CaseStatus.quote)
        assert len(quotes) == 1
        assert quotes[0].case_number == "101/2024"
