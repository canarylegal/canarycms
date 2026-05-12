"""Emit a sample Letter precedent .docx with merge tokens (run manually; not used by the app)."""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document


def main() -> None:
    out = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path("Universal-letter-precedent.docx")

    doc = Document()
    names_row = (
        "[TITLE] [FIRST_INITIAL] [MIDDLE_INITIAL] [LAST_NAME] "
        "[TITLE_2] [FIRST_INITIAL_2] [MIDDLE_INITIAL_2] [LAST_NAME_2] "
        "[TITLE_3] [FIRST_INITIAL_3] [MIDDLE_INITIAL_3] [LAST_NAME_3] "
        "[TITLE_4] [FIRST_INITIAL_4] [MIDDLE_INITIAL_4] [LAST_NAME_4]"
    )
    # Single paragraph so Word does not insert spacing between the names row and org/address block.
    doc.add_paragraph(f"{names_row}\n[ORG_AND_ADDRESS_BLOCK]")
    body = [
        "",
        "[DATE]",
        "",
        "Your Ref: [CONTACT_REF]",
        "Our Ref: [FEE_EARNER_INITIALS]/[CASE_REF]",
        "",
        "[PRIMARY_CLIENT_LETTER_DEAR]",
        "",
        "Re: [MATTER_DESCRIPTION]",
        "",
    ]
    for line in body:
        doc.add_paragraph(line)

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    print(out)


if __name__ == "__main__":
    main()
