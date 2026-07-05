"""Portal form e-mail links."""

from __future__ import annotations

import uuid

from app.alert_templates import portal_form_sent
from app.portal_form_service import form_link_for_submission


def test_form_link_for_submission_uses_short_path(monkeypatch):
    monkeypatch.setattr("app.portal_form_service.portal_public_url", lambda: "https://example.test/portal")
    submission_id = uuid.UUID("c94d2b11-7e93-4f51-8abc-daa53412162f")
    assert form_link_for_submission(submission_id) == (
        "https://example.test/portal/f/c94d2b11-7e93-4f51-8abc-daa53412162f"
    )


def test_portal_form_sent_html_uses_form_link():
    submission_id = uuid.uuid4()
    portal_url = f"https://example.test/portal/f/{submission_id}"
    subject, body, html = portal_form_sent(
        firm_name="Ashbourne & Finch",
        contact_name="Alex Brown",
        form_name="Client details",
        matter_label="Purchase of 682 Park Avenue",
        portal_url=portal_url,
    )
    assert subject.startswith("Form to complete — ")
    assert "Complete form:" in body
    assert f'href="{portal_url}"' in html
    assert "Complete form" in html
    assert len(portal_url) < 120
