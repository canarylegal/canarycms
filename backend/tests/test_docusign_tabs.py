"""DocuSign default tab placement for non-template sends."""

from __future__ import annotations

from app.docusign_tabs import signer_tabs_for_document


def test_signer_tabs_use_integer_page_number() -> None:
    tabs = signer_tabs_for_document(
        recipient_id="1",
        document_id="1",
        signer_index=1,
        page_number=3,
    )
    sign = tabs["signHereTabs"][0]
    date = tabs["dateSignedTabs"][0]
    assert sign["pageNumber"] == "3"
    assert sign["recipientId"] == "1"
    assert sign["documentId"] == "1"
    assert sign["xPosition"] == "72"
    assert date["pageNumber"] == "3"


def test_page_number_never_below_one() -> None:
    tabs = signer_tabs_for_document(
        recipient_id="1",
        document_id="1",
        signer_index=1,
        page_number=0,
    )
    assert tabs["signHereTabs"][0]["pageNumber"] == "1"


def test_multiple_signers_stack_vertically() -> None:
    t1 = signer_tabs_for_document(
        recipient_id="1",
        document_id="1",
        signer_index=1,
        page_number=2,
    )
    t2 = signer_tabs_for_document(
        recipient_id="2",
        document_id="1",
        signer_index=2,
        page_number=2,
    )
    y1 = int(t1["signHereTabs"][0]["yPosition"])
    y2 = int(t2["signHereTabs"][0]["yPosition"])
    assert y2 < y1
