"""Core shim — DocuSign tab helpers (commercial package when attached).

Pure fallback kept in Core so unit tests collect without the commercial package.
"""

from __future__ import annotations

from typing import Any

from app.commercial_runtime import reexport_commercial

if not reexport_commercial(globals(), "canary_commercial.docusign_tabs"):

    def signer_tabs_for_document(
        *,
        recipient_id: str,
        document_id: str,
        signer_index: int,
        page_number: int,
    ) -> dict[str, list[dict[str, Any]]]:
        """Place Sign here + Date signed on ``page_number`` for each signer (1-based index)."""
        page = str(max(1, page_number))
        row = max(0, signer_index - 1)
        y = 680 - (row * 95)
        common = {
            "documentId": document_id,
            "pageNumber": page,
            "recipientId": recipient_id,
        }
        return {
            "signHereTabs": [
                {
                    **common,
                    "xPosition": "72",
                    "yPosition": str(y),
                    "tabLabel": f"SignHere{signer_index}",
                }
            ],
            "dateSignedTabs": [
                {
                    **common,
                    "xPosition": "300",
                    "yPosition": str(y + 18),
                    "tabLabel": f"DateSigned{signer_index}",
                }
            ],
        }
