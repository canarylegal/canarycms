"""Quote portal e-mail links and templates."""

from __future__ import annotations

import uuid

from app.alert_templates import (
    portal_contact_access_granted,
    portal_contact_files_added,
    portal_form_sent,
    portal_login_otp,
    portal_quote_sent,
)
from app.quote_portal_service import quote_link_for_delivery


def test_quote_link_for_delivery_uses_short_path(monkeypatch):
    monkeypatch.setattr("app.quote_portal_service.portal_public_url", lambda: "https://example.test/portal")
    delivery_id = uuid.UUID("b84c1b00-6d82-4e40-95cd-daa53412162f")
    assert quote_link_for_delivery(delivery_id) == (
        "https://example.test/portal/q/b84c1b00-6d82-4e40-95cd-daa53412162f"
    )


def _assert_portal_html_has_cta(html: str, url: str, label: str) -> None:
    assert f'href="{url}"' in html
    assert label in html
    assert "#0891b2" in html
    assert "If the button does not work" in html


def test_portal_quote_sent_html_uses_cta_button():
    delivery_id = uuid.uuid4()
    portal_url = f"https://example.test/portal/q/{delivery_id}"
    subject, body, html = portal_quote_sent(
        firm_name="Ashbourne & Finch",
        contact_name="Alex Brown",
        quote_filename="Quote — All clients.docx",
        matter_label="Purchase of 682 Park Avenue",
        portal_url=portal_url,
    )
    assert subject.startswith("Quote — ")
    assert "View your quote:" in body
    _assert_portal_html_has_cta(html, portal_url, "View your quote")
    assert len(portal_url) < 120


def test_portal_client_emails_use_styled_cta():
    portal_url = "https://example.test/portal"
    _, _, access_html = portal_contact_access_granted(
        firm_name="Firm",
        contact_name="Alex",
        portal_url=portal_url,
        access_code="ABC123",
    )
    _assert_portal_html_has_cta(access_html, portal_url, "Open client portal")
    assert "Your access code" in access_html
    assert "ABC123" in access_html

    _, _, form_html = portal_form_sent(
        firm_name="Firm",
        contact_name="Alex",
        form_name="Client details",
        matter_label="Purchase",
        portal_url=portal_url,
    )
    _assert_portal_html_has_cta(form_html, portal_url, "Complete form")

    _, _, files_html = portal_contact_files_added(
        firm_name="Firm",
        contact_name="Alex",
        area_label="Documents",
        filenames=["Letter.pdf"],
        portal_url=portal_url,
    )
    _assert_portal_html_has_cta(files_html, portal_url, "View documents")
    assert "Letter.pdf" in files_html

    _, _, otp_html = portal_login_otp(
        firm_name="Firm",
        contact_name="Alex",
        portal_url=portal_url,
        otp_code="123456",
    )
    _assert_portal_html_has_cta(otp_html, portal_url, "Sign in to portal")
    assert "123456" in otp_html
