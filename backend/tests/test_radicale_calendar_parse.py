"""Unit tests for Radicale calendar URL/ref helpers (no CalDAV network)."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.radicale_calendar import href_to_ref, parse_event_href, ref_to_href


def test_href_ref_round_trip() -> None:
    href = f"/{uuid.uuid4()}/canary/event-abc.ics"
    ref = href_to_ref(href)
    assert "=" not in ref
    assert ref_to_href(ref) == href


def test_href_ref_round_trip_with_queryish_chars() -> None:
    href = "/owner/cal-slug/path%20with%20spaces.ics"
    assert ref_to_href(href_to_ref(href)) == href


def test_parse_event_href_valid() -> None:
    owner = uuid.uuid4()
    slug = "canary"
    href = f"http://radicale:5232/{owner}/{slug}/evt-1.ics"
    got_owner, got_slug = parse_event_href(href)
    assert got_owner == owner
    assert got_slug == slug


def test_parse_event_href_path_only() -> None:
    owner = uuid.uuid4()
    href = f"/{owner}/work/item.ics"
    got_owner, got_slug = parse_event_href(href)
    assert got_owner == owner
    assert got_slug == "work"


def test_parse_event_href_invalid_short() -> None:
    with pytest.raises(HTTPException) as exc:
        parse_event_href("/only-one")
    assert exc.value.status_code == 400


def test_parse_event_href_invalid_uuid() -> None:
    with pytest.raises(HTTPException) as exc:
        parse_event_href("/not-a-uuid/canary/e.ics")
    assert exc.value.status_code == 400
