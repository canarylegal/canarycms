"""Portal quote PDF snapshot generation."""

from __future__ import annotations

import uuid
from app.quote_portal_pdf import portal_quote_pdf_filename


def test_portal_quote_pdf_filename_strips_extension() -> None:
    from types import SimpleNamespace

    row = SimpleNamespace(original_filename="Quote — All clients.docx")
    assert portal_quote_pdf_filename(row) == "Quote — All clients.pdf"


def test_portal_quote_pdf_filename_for_pdf_source() -> None:
    from types import SimpleNamespace

    row = SimpleNamespace(original_filename="Quote.pdf")
    assert portal_quote_pdf_filename(row) == "Quote.pdf"


def test_parse_onlyoffice_convert_xml_response() -> None:
    from app.quote_portal_pdf import _parse_onlyoffice_convert_response

    raw = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<FileResult><FileUrl>http://onlyoffice/cache/out.pdf</FileUrl>"
        "<EndConvert>True</EndConvert></FileResult>"
    )
    data = _parse_onlyoffice_convert_response(raw)
    assert data["FileUrl"] == "http://onlyoffice/cache/out.pdf"
    assert data["EndConvert"] == "True"


def test_portal_quote_delivery_view_prefers_pdf_metadata() -> None:
    from types import SimpleNamespace

    from app.models import QuotePortalDeliveryStatus
    from app.quote_portal_service import portal_quote_delivery_view

    delivery = SimpleNamespace(
        id=uuid.uuid4(),
        file_id=uuid.uuid4(),
        grant_id=None,
        case_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        portal_pdf_file_id=uuid.uuid4(),
        status=QuotePortalDeliveryStatus.pending,
        decline_reason=None,
        responded_at=None,
        file_version_at_send=1,
    )
    source = SimpleNamespace(
        original_filename="Quote.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=1000,
        folder_path="Quotes",
        version=1,
    )
    pdf = SimpleNamespace(
        original_filename="Quote.pdf",
        mime_type="application/pdf",
        size_bytes=500,
    )
    case = SimpleNamespace(title="Test matter")

    class FakeSession:
        def get(self, model, key):
            if key == delivery.file_id:
                return source
            if key == delivery.portal_pdf_file_id:
                return pdf
            if key == delivery.case_id:
                return case
            return None

    out = portal_quote_delivery_view(FakeSession(), delivery, grant=None)
    assert out["original_filename"] == "Quote.pdf"
    assert out["mime_type"] == "application/pdf"
    assert out["portal_pdf_available"] is True
