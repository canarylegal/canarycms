"""E-mail compose subject uses matter description, not precedent title."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.routers.files import _case_email_compose_bundle
from app.schemas import CaseEmailDraftM365In


def test_email_compose_subject_uses_matter_title_not_precedent_name(monkeypatch) -> None:
    case_id = uuid.uuid4()
    precedent_id = uuid.uuid4()
    case_row = SimpleNamespace(title="Purchase of 1 High Street", case_number="000001")
    precedent = SimpleNamespace(name="Client update e-mail")

    class FakeDb:
        def get(self, model, pk):
            name = getattr(model, "__name__", str(model))
            if name.endswith("Case") or name == "Case":
                return case_row if pk == case_id else None
            if name.endswith("Precedent") or name == "Precedent":
                return precedent if pk == precedent_id else None
            return None

    body = CaseEmailDraftM365In(
        folder="",
        precedent_id=precedent_id,
        case_contact_id=None,
        global_contact_id=None,
        precedent_merge_all_clients=False,
        attachment_file_ids=[],
    )

    monkeypatch.setattr(
        "app.routers.files.resolve_blank_email_compose_body",
        lambda _db, merge_in: merge_in,
    )
    monkeypatch.setattr(
        "app.routers.files.merge_compose_docx_bytes",
        lambda *_a, **_k: (b"docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    )
    monkeypatch.setattr(
        "app.routers.files.extract_plain_text_from_docx_bytes",
        lambda _b: "Dear Client,\n\nBody text.",
    )
    monkeypatch.setattr("app.routers.files._resolve_recipient_email_m365", lambda *_a, **_k: "")

    _to, subject, _body, _atts = _case_email_compose_bundle(case_id, body, SimpleNamespace(id=uuid.uuid4()), FakeDb())

    assert subject == "Purchase of 1 High Street"
    assert "Client update" not in subject
