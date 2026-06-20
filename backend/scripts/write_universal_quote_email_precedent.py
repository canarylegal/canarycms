#!/usr/bin/env python3
"""Emit the canonical universal quote e-mail precedent (reserved QUOTE_EMAIL).

Run manually; the bundled seed copy lives at
``backend/precedents_seed/bundle/g4_quote_email.docx``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.docx_util import write_quote_email_precedent_docx  # noqa: E402


def main() -> None:
    dest = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else _BACKEND / "precedents_seed" / "bundle" / "g4_quote_email.docx"
    )
    write_quote_email_precedent_docx(dest.resolve())
    print(f"Wrote {dest}")


if __name__ == "__main__":
    main()
